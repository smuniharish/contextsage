"""Heterogeneous context decomposition.

A single message — especially a large ``ToolMessage`` from an MCP server —
frequently mixes natural language, JSON, logs, errors, and metadata. This
module NEVER classifies a whole message as one type. Instead it splits each
message's content into regions and lets
:class:`~contextsage.classification.signals.StructuralSignalDetector` classify
each region independently, producing a flat list of
:class:`~contextsage.core.models.ContextUnit` objects.

The segmentation strategy, in order:

1. Fenced code blocks (```...```) are extracted as ``CODE`` regions.
2. Remaining text is scanned for JSON values using
   ``json.JSONDecoder.raw_decode``, which can locate a JSON value starting at
   a given index without needing to guess its end — this lets JSON blocks be
   pulled out of surrounding prose/log text cheaply and precisely.
3. What remains is split into contiguous runs of "log-like" lines vs.
   "everything else" lines, each becoming its own region.

Each region is independently re-classified by the structural signal
detector (which may further refine it into ``TABLE``/``ERROR``/``TEXT``).

Segmentation is a distinct concern from classification/parsing (it decides
*where* to cut, not *what* a region is), but the shape it looks for
(fence markers, JSON openers, severity words) must not silently drift from
whatever the configured parsers actually recognize. So none of these
patterns are duplicated here: they are derived, at construction time, from
the actual :class:`~contextsage.parsers.code_parser.CodeParser`/
:class:`~contextsage.parsers.json_parser.JSONParser`/
:class:`~contextsage.parsers.log_parser.LogParser` instances found in the
detector's registry (default or overridden via
``IntelligentSummarizationMiddleware(parsers=[...])``) — falling back to
those same parsers' own public defaults if a fully custom registry omits
one of them.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar

from contextsage.budget.tokens import TokenCounter
from contextsage.classification.signals import StructuralSignalDetector
from contextsage.core.models import ContentSignals, ContextUnit, RegionKind
from contextsage.parsers.base import ContentParser
from contextsage.parsers.code_parser import DEFAULT_CODE_FENCE_PATTERN, CodeParser
from contextsage.parsers.json_parser import DEFAULT_JSON_START_CHARACTERS, JSONParser
from contextsage.parsers.log_parser import DEFAULT_LOGLEVEL_PATTERN, LogParser

if TYPE_CHECKING:
    from collections.abc import Sequence

    from langchain_core.messages import BaseMessage


@dataclass(slots=True)
class _RawBlock:
    text: str
    hint: RegionKind | None = None


def _code_fence_block_pattern(fence_marker: str) -> re.Pattern[str]:
    """Build the full fence-block-capturing regex around one fence marker."""
    escaped = re.escape(fence_marker)
    return re.compile(rf"{escaped}[\w+-]*\n.*?{escaped}", re.DOTALL)


def _json_start_pattern(start_characters: str) -> re.Pattern[str]:
    return re.compile(f"[{re.escape(start_characters)}]")


_ParserT = TypeVar("_ParserT", bound=ContentParser)


class ContextDecomposer:
    """Splits messages into independently-classified :class:`ContextUnit` objects."""

    def __init__(
        self,
        token_counter: TokenCounter,
        detector: StructuralSignalDetector | None = None,
    ) -> None:
        self._token_counter = token_counter
        self._detector = detector or StructuralSignalDetector()

        code_parser = self._find_parser(CodeParser)
        json_parser = self._find_parser(JSONParser)
        log_parser = self._find_parser(LogParser)

        fence_marker = (
            code_parser.fence_pattern.pattern if code_parser else DEFAULT_CODE_FENCE_PATTERN.pattern
        )
        self._code_fence_re = _code_fence_block_pattern(fence_marker)
        self._json_start_re = _json_start_pattern(
            json_parser.start_characters if json_parser else DEFAULT_JSON_START_CHARACTERS
        )
        self._severity_re = log_parser.loglevel_pattern if log_parser else DEFAULT_LOGLEVEL_PATTERN

    def _find_parser(self, kind: type[_ParserT]) -> _ParserT | None:
        return next((p for p in self._detector.registry if isinstance(p, kind)), None)

    def decompose(self, messages: Sequence[BaseMessage]) -> list[ContextUnit]:
        units: list[ContextUnit] = []
        for message_index, message in enumerate(messages):
            text = _content_as_text(message)
            if not text.strip():
                continue
            role = getattr(message, "type", "unknown")
            message_id = getattr(message, "id", None)
            for position, block in enumerate(self._segment(text)):
                if not block.text.strip():
                    continue
                signals = self._classify(block)
                units.append(
                    ContextUnit(
                        unit_id=f"{message_id or message_index}:{position}",
                        message_id=message_id,
                        message_index=message_index,
                        role=role,
                        content=block.text,
                        token_count=self._token_counter.count_text(block.text),
                        position=position,
                        signals=signals,
                    )
                )
        return units

    def _classify(self, block: _RawBlock) -> ContentSignals:
        if block.hint is RegionKind.CODE:
            return ContentSignals(kind=RegionKind.CODE, confidence=0.95)
        return self._detector.detect(block.text)

    def _segment(self, text: str) -> list[_RawBlock]:
        blocks: list[_RawBlock] = []
        cursor = 0
        for match in self._code_fence_re.finditer(text):
            if match.start() > cursor:
                blocks.extend(self._segment_non_code(text[cursor : match.start()]))
            blocks.append(_RawBlock(text=match.group(0), hint=RegionKind.CODE))
            cursor = match.end()
        if cursor < len(text):
            blocks.extend(self._segment_non_code(text[cursor:]))
        return blocks

    def _segment_non_code(self, text: str) -> list[_RawBlock]:
        """Extract embedded JSON values, then split the rest into log/text runs."""
        blocks: list[_RawBlock] = []
        decoder = json.JSONDecoder()
        cursor = 0
        length = len(text)
        while cursor < length:
            match = self._json_start_re.search(text, cursor)
            if match is None:
                blocks.extend(self._segment_lines(text[cursor:]))
                break
            start = match.start()
            if start > cursor:
                blocks.extend(self._segment_lines(text[cursor:start]))
            try:
                _, end = decoder.raw_decode(text, start)
            except (json.JSONDecodeError, ValueError):
                # Not valid JSON at this position; treat the bracket character
                # itself as ordinary text and keep scanning.
                blocks.extend(self._segment_lines(text[start : start + 1]))
                cursor = start + 1
                continue
            blocks.append(_RawBlock(text=text[start:end], hint=RegionKind.JSON))
            cursor = end
        return blocks

    def _segment_lines(self, text: str) -> list[_RawBlock]:
        """Group contiguous lines into log-like vs. plain-text runs."""
        lines = text.splitlines(keepends=True)
        if not lines:
            return []
        groups: list[list[str]] = []
        current: list[str] = []
        current_is_log: bool | None = None
        for line in lines:
            is_log = bool(self._severity_re.search(line))
            if current_is_log is None or is_log == current_is_log:
                current.append(line)
                current_is_log = is_log
            else:
                groups.append(current)
                current = [line]
                current_is_log = is_log
        if current:
            groups.append(current)
        return [_RawBlock(text="".join(g)) for g in groups if "".join(g).strip()]


def _content_as_text(message: BaseMessage) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(str(block.get("text", block)))
        return "\n".join(parts)
    return str(content)
