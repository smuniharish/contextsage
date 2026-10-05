"""Split each message into content units using parsefabric."""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING

from parsefabric import ParseContext, ParseEngine

from contextsage._pipeline.lineage import is_summary
from contextsage._pipeline.models import (
    SUMMARY_ROLE,
    WARNING_RANK,
    Kind,
    ParsedJSON,
    Unit,
    canonical_severity,
    severity_rank,
)
from contextsage._pipeline.signals import find_identifiers

if TYPE_CHECKING:
    import re
    from collections.abc import Mapping, Sequence

    from langchain_core.messages import BaseMessage
    from parsefabric import ParsedEvent, Parser

_MIXED_CONTENT = "mixed-content"
_PARSER_KINDS: Mapping[str, str] = {
    "json": Kind.JSON,
    "application-log": Kind.LOG,
    "timestamped-log": Kind.LOG,
    "python-traceback": Kind.ERROR,
}
_EVENT_KINDS: Mapping[str, str] = {
    "log": Kind.LOG,
    "traceback": Kind.ERROR,
    "table": Kind.TABLE,
    "code": Kind.CODE,
    "fence": Kind.CODE,
}
_SEVERITY_KEYS = ("level", "severity", "levelname", "log_level")


def _event_kind(event: ParsedEvent) -> str:
    """Return the content kind of an event.

    Events from a routed parser take that parser's name as their kind (mapped
    for parsefabric's built-in parsers). A routed parser that does not record
    its name in the evidence contributes its event type instead.
    """
    if event.event_type == "unparsed":
        return Kind.TEXT
    parser = event.evidence.parser_name
    if parser is not None and parser != _MIXED_CONTENT:
        return _PARSER_KINDS.get(parser, parser)
    if event.event_type == "other":
        return Kind.TEXT
    return _EVENT_KINDS.get(event.event_type, event.event_type)


def _event_severity(event: ParsedEvent) -> str | None:
    severity = canonical_severity(event.severity) or canonical_severity(
        event.attributes.get("level")
    )
    if severity is None and event.event_type == "json_record":
        value = event.attributes.get("value")
        if isinstance(value, dict):
            severity = next(
                (
                    level
                    for key in _SEVERITY_KEYS
                    if (level := canonical_severity(value.get(key))) is not None
                ),
                None,
            )
    return severity


@dataclass(slots=True)
class _Segment:
    first: int
    last: int
    kind: str
    document: ParsedJSON | None = None
    block: bool = False
    elevated: bool = False


@dataclass(slots=True)
class _Lines:
    """Per-line classification of one message."""

    kinds: list[str]
    severities: list[str | None]
    blocks: dict[int, _Segment]


def _classify(lines: Sequence[str], events: Sequence[ParsedEvent]) -> _Lines:
    starts: list[int] = []
    offset = 0
    for line in lines:
        starts.append(offset)
        offset += len(line.encode("utf-8", "surrogatepass"))
    count = len(lines)
    kinds: list[str | None] = [None] * count
    severities: list[str | None] = [None] * count
    blocks: dict[int, _Segment] = {}
    fences: list[int] = []
    for event in events:
        evidence = event.evidence
        if evidence.line_number is None:
            continue
        first = min(evidence.line_number - 1, count - 1)
        end = evidence.end_offset
        last = (
            first if end is None else bisect.bisect_right(starts, max(end - 1, 0)) - 1
        )
        last = min(max(last, first), count - 1)
        kind = _event_kind(event)
        severity = _event_severity(event)
        for index in range(first, last + 1):
            if kinds[index] is None:
                kinds[index] = kind
            if severity_rank(severity) > severity_rank(severities[index]):
                severities[index] = severity
        if event.event_type == "json_record":
            blocks[first] = _Segment(
                first,
                last,
                Kind.JSON,
                ParsedJSON(event.attributes.get("value")),
                block=True,
            )
        elif event.event_type == "fence":
            fences.append(first)
    resolved = [kind or Kind.TEXT for kind in kinds]
    _join_fences(fences, resolved, blocks, count)
    _join_stack_traces(lines, resolved, severities)
    return _Lines(resolved, severities, blocks)


def _join_fences(
    fences: Sequence[int], kinds: list[str], blocks: dict[int, _Segment], count: int
) -> None:
    """Turn each fenced block, markers included, into one atomic segment."""
    for opening, closing in zip(fences[::2], [*fences[1::2], count - 1], strict=False):
        body = kinds[opening + 1 : closing]
        kind = next((kind for kind in body if kind != Kind.CODE), Kind.CODE)
        blocks[opening] = _Segment(opening, closing, kind, block=True)


def _join_stack_traces(
    lines: Sequence[str], kinds: list[str], severities: list[str | None]
) -> None:
    """Absorb indented source lines between stack-trace lines into the trace."""
    errors = [index for index, kind in enumerate(kinds) if kind == Kind.ERROR]
    for before, after in pairwise(errors):
        between = range(before + 1, after)
        if between and all(
            lines[index][:1] in (" ", "\t")
            and lines[index].strip()
            and kinds[index] in (Kind.TEXT, Kind.CODE)
            for index in between
        ):
            for index in between:
                kinds[index] = Kind.ERROR
                severities[index] = severities[index] or "ERROR"


def _segments(lines: Sequence[str], classified: _Lines) -> list[_Segment]:
    """Group the lines of a message with non-blank text into segments of one kind.

    Log lines are additionally grouped by whether they are warnings or worse,
    so that routine log runs can be compacted while the warnings and errors
    around them stay intact.
    """
    segments: list[_Segment] = []
    index = 0
    while index < len(lines):
        block = classified.blocks.get(index)
        if block is not None:
            segments.append(block)
            index = block.last + 1
            continue
        if not lines[index].strip():
            if segments:
                segments[-1].last = index
            index += 1
            continue
        kind = classified.kinds[index]
        elevated = (
            kind == Kind.LOG
            and severity_rank(classified.severities[index]) >= WARNING_RANK
        )
        previous = segments[-1] if segments else None
        if (
            previous is not None
            and not previous.block
            and previous.kind == kind
            and previous.elevated == elevated
        ):
            previous.last = index
        else:
            segments.append(_Segment(index, index, kind, elevated=elevated))
        index += 1
    segments[0].first = 0
    return segments


class Decomposer:
    """Turns messages into `Unit` objects that tile each message's text.

    Every message is parsed independently with the configured parsefabric
    parser. Consecutive lines of the same kind form one unit; each JSON
    document and each fenced block is its own unit; blank lines join the unit
    before them. A message that cannot be parsed becomes a single text unit.

    Args:
        parser: The parsefabric parser for message text.
        identifier_patterns: Patterns whose matches are must-keep identifiers.
    """

    def __init__(
        self, parser: Parser, identifier_patterns: Sequence[re.Pattern[str]]
    ) -> None:
        self._parser = parser
        self._engine = ParseEngine()
        self._identifier_patterns = tuple(identifier_patterns)

    async def decompose(self, messages: Sequence[BaseMessage]) -> tuple[Unit, ...]:
        """Return the units of every message with non-blank text, in order."""
        units: list[Unit] = []
        for index, message in enumerate(messages):
            text = message.text
            if text.strip():
                units.extend(await self._decompose_message(index, message, text))
        return tuple(units)

    async def _decompose_message(
        self, index: int, message: BaseMessage, text: str
    ) -> list[Unit]:
        lines = text.splitlines(keepends=True)
        result = await self._engine.parse(
            self._parser,
            text,
            ParseContext(source_id=f"message-{index}"),
            continue_on_error=True,
        )
        if result.events:
            classified = _classify(lines, result.events)
            segments = _segments(lines, classified)
            severities = classified.severities
        else:
            segments = [_Segment(0, len(lines) - 1, Kind.TEXT)]
            severities = [None] * len(lines)
        key = message.id or f"message-{index}"
        role = SUMMARY_ROLE if is_summary(message) else message.type
        units: list[Unit] = []
        for position, segment in enumerate(segments):
            unit_text = "".join(lines[segment.first : segment.last + 1])
            identifiers, identifier_lines = find_identifiers(
                unit_text, self._identifier_patterns
            )
            units.append(
                Unit(
                    unit_id=f"{key}:{position}",
                    message_index=index,
                    role=role,
                    kind=segment.kind,
                    text=unit_text,
                    first_line=segment.first + 1,
                    line_severities=tuple(severities[segment.first : segment.last + 1]),
                    identifiers=identifiers,
                    document=segment.document,
                    identifier_lines=identifier_lines,
                )
            )
        return units
