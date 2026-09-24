"""Importance engine.

Importance is a composite signal, not simply recency. Each rule below
contributes a bounded amount to a unit's score and records *why* (the
``reasons`` tuple), which powers observability and lets validation/tests
assert on causes rather than opaque numbers.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import replace

from contextsage.classification.signals import normalize_for_repetition
from contextsage.core.models import ContextUnit, ImportanceScore

_CORRECTION_RE = re.compile(
    r"\b(no[,.]|not\b|instead of|use .+ instead|don'?t use|actually,? use|"
    r"i meant|correction:|change (it |that )?to|switch to)\b",
    re.IGNORECASE,
)
_CONSTRAINT_RE = re.compile(
    r"\b(must|never|always|required|do not|don'?t|constraint|mandatory|"
    r"only use|forbidden)\b",
    re.IGNORECASE,
)
_DECISION_RE = re.compile(
    r"\b(decision|recommend|conclu(de|sion)|approved|denied|rejected)\b", re.I
)
_HIGH_SEVERITY = {"ERROR", "CRITICAL", "FATAL"}

# Weight budget; each contribution is bounded so the composite always fits [0, 1]
# after clamping.
_RECENCY_WEIGHT = 0.25
_CORRECTION_WEIGHT = 0.9
_CONSTRAINT_WEIGHT = 0.25
_ERROR_WEIGHT = 0.35
_DECISION_WEIGHT = 0.2
_IDENTIFIER_WEIGHT = 0.1
_IDENTIFIER_IN_ERROR_CONTEXT_WEIGHT = 0.35
_REPETITION_GROUP_MIN_SIZE = 3
_REPETITION_PENALTY_FLOOR = 0.05
_RECENCY_THRESHOLD_FOR_REASON = 0.8


class ImportanceEngine:
    """Assigns an :class:`ImportanceScore` to every context unit."""

    def score(self, units: list[ContextUnit]) -> list[ContextUnit]:
        if not units:
            return units

        repetition_groups = self._group_repetitions(units)
        max_index = max((u.message_index for u in units), default=0) or 1

        scored: list[ContextUnit] = []
        for unit in units:
            value = 0.0
            reasons: list[str] = []

            recency = unit.message_index / max_index
            value += recency * _RECENCY_WEIGHT
            if recency > _RECENCY_THRESHOLD_FOR_REASON:
                reasons.append("recent")

            is_correction = unit.role == "human" and _CORRECTION_RE.search(unit.content)
            if is_correction:
                value += _CORRECTION_WEIGHT
                reasons.append("user_correction")

            if _CONSTRAINT_RE.search(unit.content):
                value += _CONSTRAINT_WEIGHT
                reasons.append("active_constraint_or_instruction")

            if unit.signals.has_error and (unit.signals.severity or "") in _HIGH_SEVERITY:
                value += _ERROR_WEIGHT
                reasons.append("error_severity")

            if _DECISION_RE.search(unit.content):
                value += _DECISION_WEIGHT
                reasons.append("decision_relevance")

            if unit.signals.identifiers:
                value += _IDENTIFIER_WEIGHT
                reasons.append("contains_identifier")
                if unit.signals.has_error:
                    # An identifier (transaction/request/trace id, customer id, ...)
                    # co-occurring with an error/failure signal is a strong,
                    # context-dependent preservation signal: the identifier
                    # matters *because* it is tied to a failure, not merely
                    # because it looks like an id.
                    value += _IDENTIFIER_IN_ERROR_CONTEXT_WEIGHT
                    reasons.append("identifier_in_error_context")

            group_key = repetition_groups.get(unit.unit_id)
            group_size, group_rank = group_key if group_key else (1, 0)
            is_repetitive = group_size >= _REPETITION_GROUP_MIN_SIZE
            if is_repetitive and group_rank not in (0, group_size - 1) and not is_correction:
                value = max(_REPETITION_PENALTY_FLOOR, value * 0.2)
                reasons.append("repetitive_low_value")

            value = min(max(value, 0.0), 1.0)
            new_signals = replace(unit.signals, is_repetitive=is_repetitive)
            scored.append(
                replace(
                    unit,
                    signals=new_signals,
                    importance=ImportanceScore(value=value, reasons=tuple(reasons)),
                )
            )
        return scored

    @staticmethod
    def _group_repetitions(units: list[ContextUnit]) -> dict[str, tuple[int, int]]:
        """Map unit_id -> (group_size, rank_within_group) for near-duplicate units."""
        signatures = {unit.unit_id: normalize_for_repetition(unit.content[:200]) for unit in units}
        counts = Counter(signatures.values())
        rank_tracker: dict[str, int] = {}
        result: dict[str, tuple[int, int]] = {}
        for unit in units:
            sig = signatures[unit.unit_id]
            size = counts[sig]
            rank = rank_tracker.get(sig, 0)
            rank_tracker[sig] = rank + 1
            result[unit.unit_id] = (size, rank)
        return result
