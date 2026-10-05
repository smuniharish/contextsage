"""Detection of conflicting values reported by different messages."""

from __future__ import annotations

import re
from itertools import combinations
from typing import TYPE_CHECKING

from contextsage._pipeline.models import SUMMARY_ROLE, Contradiction, Kind
from contextsage._pipeline.validation import contains

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from contextsage._pipeline.models import Unit

MAX_DISTINCT_VALUES = 3
"""Keys with more distinct values than this are measurements, not assertions."""

_CONFLICT = 2
"""Distinct values needed for a conflict."""

_CLAIM_KINDS = frozenset({Kind.TEXT, Kind.JSON})
"""Kinds whose ``key: value`` pairs are claims. In logs, stack traces, code and
tables, differing values are records of what happened, not disagreements."""

_ASSERTION = re.compile(
    r"(?<![\w.:/@-])(?P<key>[A-Za-z][A-Za-z0-9_]{1,30})\s*[:=]\s*"
    r"(?P<quote>[\"']?)(?P<value>[A-Za-z0-9][\w.\-]{0,40})(?P=quote)"
    r"(?![\w:/.-])(?!\s*[:=])"
)
_VOLATILE_KEY = re.compile(
    r"(?:^|_)(?:id|ids|uuid|guid|key|token|hash|sha|digest|ts|time|timestamp|date|at|"
    r"ms|latency|duration|elapsed|took|count|total|size|bytes|line|port|pid|offset|"
    r"seq|version|attempt|retry|retries|page|limit|level|levelname|lvl|severity|msg|"
    r"message|logger|caller)$"
)
"""Keys whose values naturally differ: identifiers, times, measurements and
the fields of structured log records."""
_MAX_JSON_TEXT = 40


def _assertions(unit: Unit) -> Iterator[tuple[str, str]]:
    if unit.document is not None:
        value = unit.document.value
        if isinstance(value, dict):
            for key, item in value.items():
                if isinstance(item, bool):
                    text = "true" if item else "false"
                elif isinstance(item, (int, float)) or (
                    isinstance(item, str) and 0 < len(item) <= _MAX_JSON_TEXT
                ):
                    text = str(item)
                else:
                    continue
                # Escaped or reformatted values could never be found again.
                if contains(unit.text, text):
                    yield key, text
        return
    for match in _ASSERTION.finditer(unit.text):
        yield match.group("key"), match.group("value")


def find_contradictions(units: Sequence[Unit]) -> tuple[Contradiction, ...]:
    """Find keys that different messages report with different values.

    Assertions are ``key: value`` and ``key=value`` pairs in prose, and the
    top-level scalar fields of JSON objects, in messages other than summaries:
    a summary only repeats claims, so conflicts come from their sources.
    Identifiers, timestamps, counters, log fields and other naturally varying
    keys are ignored, as is any key with more than `MAX_DISTINCT_VALUES`
    distinct values, so the work stays linear in the history size.

    Args:
        units: Units in history order.

    Returns:
        One contradiction per pair of distinct values from different messages,
        the earlier value first.
    """
    seen: dict[str, dict[str, tuple[Unit, str]] | None] = {}
    for unit in units:
        if unit.kind not in _CLAIM_KINDS or unit.role == SUMMARY_ROLE:
            continue
        for key, value in _assertions(unit):
            folded_key = key.casefold()
            if _VOLATILE_KEY.search(folded_key):
                continue
            values = seen.setdefault(folded_key, {})
            if values is None:
                continue
            folded_value = value.casefold()
            if folded_value in values:
                continue
            if len(values) == MAX_DISTINCT_VALUES:
                seen[folded_key] = None
                continue
            values[folded_value] = (unit, value)
    contradictions: list[Contradiction] = []
    for key, values in seen.items():
        if not values or len(values) < _CONFLICT:
            continue
        for (unit_a, value_a), (unit_b, value_b) in combinations(values.values(), 2):
            if unit_a.message_index != unit_b.message_index:
                contradictions.append(
                    Contradiction(key, unit_a.unit_id, value_a, unit_b.unit_id, value_b)
                )
    return tuple(contradictions)
