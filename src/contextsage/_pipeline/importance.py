"""Importance scoring: a bounded composite of independent, explainable signals."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from contextsage._pipeline.models import Importance, Kind
from contextsage._pipeline.signals import mentions_failure, normalize_volatile

if TYPE_CHECKING:
    from collections.abc import Sequence

    from contextsage._pipeline.models import Unit

INSTRUCTION_ROLES = frozenset({"human", "system"})

CORRECTION = re.compile(
    r"\binstead\s+of\b"
    r"|\buse\s++[^.,;!?\n]{1,60}?\s++instead\b"
    r"|\bdo(?:n'?t|\s+not)\s+use\b"
    r"|\bactually,?\s+(?:use|it'?s|i\s+meant|make\s+it)\b"
    r"|\bi\s+meant\b"
    r"|\bcorrection:"
    r"|\bchange\s+(?:it|that|this)\s+to\b"
    r"|\bswitch\s+to\b"
    r"|(?:^|(?<=[.!?]\s))no,\s+(?:use|it'?s|that'?s|make|i\b)",
    re.IGNORECASE | re.MULTILINE,
)
"""Phrasing that corrects an earlier value; a bare "not" or "no" does not count."""

CONSTRAINT = re.compile(
    r"\b(?:must(?:\s+not)?|never|always|required|mandatory|forbidden|prohibited|"
    r"do\s+not|don'?t|only\s+use|make\s+sure|ensure)\b",
    re.IGNORECASE,
)
"""Phrasing of an instruction that must keep holding."""

DECISION = re.compile(
    r"\b(?:decision|decided|recommend(?:ed|ation)?|conclu(?:de|ded|sion)|approved|"
    r"rejected|denied|agreed)\b",
    re.IGNORECASE,
)

_RECENCY_WEIGHT = 0.25
_CORRECTION_WEIGHT = 0.9
_CONSTRAINT_WEIGHT = 0.75
_ERROR_WEIGHT = 0.35
_DECISION_WEIGHT = 0.2
_IDENTIFIER_WEIGHT = 0.1
_IDENTIFIER_IN_FAILURE_WEIGHT = 0.35
_RECENT = 0.8
_REPEAT_GROUP_MIN = 3
_REPEAT_FACTOR = 0.2
_REPEAT_FLOOR = 0.05


def normalize_apostrophes(text: str) -> str:
    """Replace typographic apostrophes (U+2018, U+2019) with ASCII ones."""
    return text.replace("\u2019", "'").replace("\u2018", "'")


def _repeated(units: Sequence[Unit]) -> set[str]:
    """Middle units of runs of three or more near-duplicates.

    Near-duplicates have the same kind and the same identifiers, and the same
    text once timestamps, hexadecimal IDs and numbers are masked. Only units
    that share their kind and identifiers are normalized and compared.
    """
    candidates: dict[tuple[str, tuple[str, ...]], list[Unit]] = {}
    for unit in units:
        candidates.setdefault((unit.kind, unit.identifiers), []).append(unit)
    repeated: set[str] = set()
    for group in candidates.values():
        if len(group) < _REPEAT_GROUP_MIN:
            continue
        duplicates: dict[str, list[str]] = {}
        for unit in group:
            duplicates.setdefault(normalize_volatile(unit.text), []).append(
                unit.unit_id
            )
        for unit_ids in duplicates.values():
            if len(unit_ids) >= _REPEAT_GROUP_MIN:
                repeated.update(unit_ids[1:-1])
    return repeated


def score(units: Sequence[Unit]) -> dict[str, Importance]:
    """Score every unit.

    Signals: recency, user corrections, standing instructions, error severity,
    decision language, and identifiers, which weigh more in the context of a
    failure and are always kept when the user states them. Prose shares the
    failure context of its whole message, so the heading of a failing tool
    result counts; logs, tables and JSON rely on their own severity and
    content. Near-duplicate units in the middle of a run of three or more are
    marked repetitive and heavily discounted, unless they are corrections.

    Args:
        units: Units in history order.

    Returns:
        The importance of each unit, by unit ID, with values in ``[0, 1]``.
    """
    if not units:
        return {}
    last_message = max(unit.message_index for unit in units) or 1
    repeated = _repeated(units)
    reports_failure = {
        unit.unit_id
        for unit in units
        if unit.kind != Kind.LOG and mentions_failure(unit.text)
    }
    failing_messages = {
        unit.message_index
        for unit in units
        if unit.has_error or unit.unit_id in reports_failure
    }
    scores: dict[str, Importance] = {}
    for unit in units:
        text = normalize_apostrophes(unit.text)
        reasons: set[str] = set()
        recency = unit.message_index / last_message
        value = recency * _RECENCY_WEIGHT
        if recency > _RECENT:
            reasons.add("recent")
        correction = unit.role == "human" and CORRECTION.search(text) is not None
        if correction:
            value += _CORRECTION_WEIGHT
            reasons.add("user_correction")
        if unit.role in INSTRUCTION_ROLES and CONSTRAINT.search(text):
            value += _CONSTRAINT_WEIGHT
            reasons.add("active_constraint")
        if unit.has_error:
            value += _ERROR_WEIGHT
            reasons.add("error_severity")
        if DECISION.search(text):
            value += _DECISION_WEIGHT
            reasons.add("decision")
        if unit.identifiers:
            value += _IDENTIFIER_WEIGHT
            reasons.add("contains_identifier")
            if unit.role == "human":
                reasons.add("user_identifier")
            failure_context = (
                unit.has_error
                or unit.unit_id in reports_failure
                or (unit.kind == Kind.TEXT and unit.message_index in failing_messages)
            )
            if failure_context:
                value += _IDENTIFIER_IN_FAILURE_WEIGHT
                reasons.add("identifier_in_failure_context")
        if unit.unit_id in repeated and not correction:
            value = max(_REPEAT_FLOOR, value * _REPEAT_FACTOR)
            reasons.add("repetitive_low_value")
        scores[unit.unit_id] = Importance(min(value, 1.0), frozenset(reasons))
    return scores
