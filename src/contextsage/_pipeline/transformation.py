"""Deterministic, signal-preserving compaction of structured content."""

from __future__ import annotations

import json
import logging
from itertools import groupby
from typing import TYPE_CHECKING

from contextsage._pipeline.models import WARNING_RANK, Kind, Preservation, severity_rank
from contextsage._pipeline.signals import mask_numbers, mask_volatile

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from langchain_core.messages import BaseMessage

    from contextsage._pipeline.models import Unit
    from contextsage._pipeline.preservation import Policy

logger = logging.getLogger("contextsage")

LOSSLESS_KINDS = frozenset({Kind.TABLE, Kind.JSON})
"""Kinds whose compaction can be lossless, so any unit of them qualifies."""

_MIN_RUN = 3
_SAMPLE = 5
_REPEATED = "__repeated__"
_OMITTED = "__omitted__"


def plan(
    units: Sequence[Unit],
    preservation: Mapping[str, Preservation],
    messages: Sequence[BaseMessage],
) -> tuple[tuple[Unit, bool], ...]:
    """Select the units to compact and whether lossy compaction is allowed.

    Table and JSON units always qualify, because their compaction can be
    lossless: minified JSON, and counted runs of identical items and rows.
    Lossy compaction (collapsing similar log lines, and grouping or sampling
    JSON lists under ``maximum_compression``) is allowed only for compressible
    units, so log units qualify only when compressible. System messages and
    messages with structured (non-string) content are never rewritten.

    Returns:
        ``(unit, lossy)`` pairs in history order.
    """
    selected: list[tuple[Unit, bool]] = []
    for unit in units:
        if unit.role == "system" or not isinstance(
            messages[unit.message_index].content, str
        ):
            continue
        lossy = preservation[unit.unit_id] is Preservation.COMPRESSIBLE
        if unit.kind in LOSSLESS_KINDS or (unit.kind == Kind.LOG and lossy):
            selected.append((unit, lossy))
    return tuple(selected)


def _log_keys(unit: Unit, lines: Sequence[str]) -> list[str | None]:
    """Similarity keys of log lines; ``None`` for lines that never collapse.

    Masking runs once over the whole unit rather than line by line.
    """
    stable = mask_volatile(unit.text)
    with_numbers = stable.splitlines()
    without_numbers = mask_numbers(stable).splitlines()
    keys: list[str | None] = []
    for index, (line, severity) in enumerate(
        zip(lines, unit.line_severities, strict=True)
    ):
        if index in unit.identifier_lines or not line.strip():
            keys.append(None)
            continue
        masked = (
            with_numbers if severity_rank(severity) >= WARNING_RANK else without_numbers
        )
        keys.append(" ".join(masked[index].split()))
    return keys


def _terminator(line: str) -> str:
    return line[len(line.rstrip("\r\n")) :] or "\n"


def collapse_repeats(unit: Unit) -> str:
    """Collapse runs of similar consecutive lines, keeping each run's ends.

    Log lines are similar when they differ only in timestamps, hexadecimal IDs
    and (below warning level) numbers; table rows only when identical. Lines
    with an identifier and blank lines are never collapsed. A run of three or
    more similar lines keeps its first and last line and replaces the rest
    with a marker naming the omitted line range.

    Returns:
        The compacted text.
    """
    lines = unit.text.splitlines(keepends=True)
    keys = (
        [line.strip() or None for line in lines]
        if unit.kind == Kind.TABLE
        else _log_keys(unit, lines)
    )
    output: list[str] = []
    for key, group in groupby(range(len(lines)), key=keys.__getitem__):
        indexes = list(group)
        omitted = indexes[1:-1]
        first, last = indexes[0], indexes[-1]
        marker = (
            f"... {len(omitted)} similar lines omitted "
            f"(lines {unit.first_line + first + 1}-{unit.first_line + last - 1}) ..."
            f"{_terminator(lines[first])}"
        )
        if (
            key is None
            or len(indexes) < _MIN_RUN
            or sum(len(lines[index]) for index in omitted) <= len(marker)
        ):
            output.extend(lines[index] for index in indexes)
        else:
            output.extend((lines[first], marker, lines[last]))
    return "".join(output)


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _compact_list(items: list[object], *, sample: bool) -> list[object]:
    """Collapse identical items and sample long lists, only where that is shorter.

    Items that are not collapsed keep their original order.
    """
    keys = [_canonical(item) for item in items]
    if sample:
        positions: dict[str, list[int]] = {}
        for index, key in enumerate(keys):
            positions.setdefault(key, []).append(index)
        groups = list(positions.values())
    else:
        groups = [
            [index for index, _ in run]
            for _, run in groupby(enumerate(keys), key=lambda pair: pair[1])
        ]
    markers: dict[int, object] = {}
    skipped: set[int] = set()
    for indexes in groups:
        count = len(indexes)
        if count == 1:
            continue
        item = items[indexes[0]]
        marker = {_REPEATED: count, "value": item}
        if len(_dumps(marker)) < len(_dumps(item)) * count + count - 1:
            markers[indexes[0]] = marker
            skipped.update(indexes[1:])
    output = [
        markers.get(index, item)
        for index, item in enumerate(items)
        if index not in skipped
    ]
    if sample and len(output) > 2 * _SAMPLE:
        middle = output[_SAMPLE:-_SAMPLE]
        marker = {_OMITTED: len(middle)}
        middle_length = sum(len(_dumps(item)) for item in middle) + len(middle) - 1
        if len(_dumps(marker)) < middle_length:
            output = [*output[:_SAMPLE], marker, *output[-_SAMPLE:]]
    return output


def _compact_value(value: object, *, sample: bool) -> object:
    if isinstance(value, dict):
        return {key: _compact_value(item, sample=sample) for key, item in value.items()}
    if isinstance(value, list):
        return _compact_list(
            [_compact_value(item, sample=sample) for item in value], sample=sample
        )
    return value


def compact_json(value: object, policy: Policy) -> str:
    """Re-serialize a JSON document compactly according to the policy.

    - ``maximum_preservation``: minify only.
    - ``balanced``: also collapse runs of identical consecutive list items into
      ``{"__repeated__": n, "value": item}``, which loses nothing.
    - ``maximum_compression``: collapse identical items anywhere in a list, and
      keep only the first and last five entries of long lists, with
      ``{"__omitted__": n}`` in between.

    A run is collapsed, and a list sampled, only when the result is shorter.

    Returns:
        The compact JSON text.
    """
    if policy != "maximum_preservation":
        value = _compact_value(value, sample=policy == "maximum_compression")
    return _dumps(value)


def compact(unit: Unit, *, policy: Policy, lossy: bool) -> str | None:
    """Return the compacted text of ``unit``, or ``None`` to keep it unchanged.

    Without ``lossy``, a ``maximum_compression`` policy compacts JSON like
    ``balanced``, which loses nothing. Compaction that fails or does not make
    the text shorter is discarded, so the original content is never at risk.
    """
    try:
        if unit.kind == Kind.JSON:
            if unit.document is None:
                return None
            effective = (
                "balanced" if policy == "maximum_compression" and not lossy else policy
            )
            core = compact_json(unit.document.value, effective)
            leading = unit.text[: len(unit.text) - len(unit.text.lstrip())]
            new_text = leading + core + unit.text[len(unit.text.rstrip()) :]
        else:
            new_text = collapse_repeats(unit)
    except Exception:
        logger.warning(
            "contextsage could not compact a %s unit; it is kept unchanged",
            unit.kind,
            exc_info=True,
        )
        return None
    return new_text if len(new_text) < len(unit.text) else None
