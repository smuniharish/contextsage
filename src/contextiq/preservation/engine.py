"""Preservation engine.

Converts importance scores and relationships into explicit
:class:`~contextiq.core.models.PreservationLevel` assignments, and extracts
concrete, literal "must survive" facts (identifiers, corrected values,
constraint sentences) that the validator later checks for in the produced
summary text.

Preservation is context-dependent: a unit is not
``MUST_PRESERVE`` merely because it contains an identifier. It becomes
``MUST_PRESERVE`` because it is a user correction, part of a contradiction,
a high-severity error, or otherwise scores highly on importance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Literal

from contextiq.core.models import ContextUnit, PreservationLevel, Relationship, RelationType

_ERROR_MUST_PRESERVE_THRESHOLD = 0.6
_CORRECTION_REFERENT_RE = re.compile(
    r"(?:instead of|not)\s+([\w.\-]+)|use\s+([\w.\-]+)\s+instead", re.IGNORECASE
)

Policy = Literal["balanced", "maximum_preservation", "maximum_compression"]


@dataclass(frozen=True, slots=True)
class _Thresholds:
    """Importance-value cut points, tunable per :data:`Policy`.

    ``maximum_preservation`` lowers the bar for MUST/SHOULD preserve (more
    content survives untouched); ``maximum_compression`` raises it (more
    content becomes a compression/summarization candidate). Content that is
    MUST_PRESERVE for a *structural* reason (user correction, contradiction,
    identifier tied to an error) is never affected by policy — only the
    numeric-importance fallback path is.
    """

    must_preserve: float
    should_preserve: float
    error_must_preserve: float


_POLICY_THRESHOLDS: dict[Policy, _Thresholds] = {
    "balanced": _Thresholds(
        must_preserve=0.75, should_preserve=0.45, error_must_preserve=_ERROR_MUST_PRESERVE_THRESHOLD
    ),
    "maximum_preservation": _Thresholds(
        must_preserve=0.60, should_preserve=0.30, error_must_preserve=0.45
    ),
    "maximum_compression": _Thresholds(
        must_preserve=0.90, should_preserve=0.65, error_must_preserve=0.80
    ),
}


class PreservationEngine:
    """Assigns preservation levels and extracts literal must-preserve facts."""

    def __init__(self, policy: Policy = "balanced") -> None:
        self._thresholds = _POLICY_THRESHOLDS[policy]

    def classify(
        self, units: list[ContextUnit], relationships: list[Relationship]
    ) -> list[ContextUnit]:
        flagged_ids = self._relationship_flagged_ids(relationships)
        thresholds = self._thresholds

        classified: list[ContextUnit] = []
        for unit in units:
            reasons = unit.importance.reasons if unit.importance else ()
            value = unit.importance.value if unit.importance else 0.0

            if "repetitive_low_value" in reasons:
                level = PreservationLevel.SAFE_TO_DROP
            elif (
                unit.unit_id in flagged_ids
                or "user_correction" in reasons
                or "identifier_in_error_context" in reasons
                or ("error_severity" in reasons and value >= thresholds.error_must_preserve)
                or value >= thresholds.must_preserve
            ):
                level = PreservationLevel.MUST_PRESERVE
            elif value >= thresholds.should_preserve:
                level = PreservationLevel.SHOULD_PRESERVE
            elif unit.signals.is_repetitive:
                level = PreservationLevel.REDUNDANT
            else:
                level = PreservationLevel.COMPRESSIBLE

            classified.append(replace(unit, preservation=level))
        return classified

    @staticmethod
    def _relationship_flagged_ids(relationships: list[Relationship]) -> set[str]:
        flagged: set[str] = set()
        for rel in relationships:
            if rel.relation in (RelationType.CONTRADICTS, RelationType.CORRECTED_BY):
                flagged.add(rel.source_unit_id)
                flagged.add(rel.target_unit_id)
        return flagged

    def extract_must_preserve_facts(self, units: list[ContextUnit]) -> tuple[str, ...]:
        """Extract concrete literal facts that validation must find in the summary."""
        facts: list[str] = []
        for unit in units:
            if unit.preservation is not PreservationLevel.MUST_PRESERVE:
                continue
            facts.extend(unit.signals.identifiers)
            reasons = unit.importance.reasons if unit.importance else ()
            if "user_correction" in reasons:
                match = _CORRECTION_REFERENT_RE.search(unit.content)
                if match:
                    referent = next(g for g in match.groups() if g)
                    facts.append(referent)
            if "active_constraint_or_instruction" in reasons:
                snippet = unit.content.strip().splitlines()[0][:160]
                facts.append(snippet)
        # De-duplicate while preserving order.
        seen: set[str] = set()
        unique: list[str] = []
        for fact in facts:
            if fact and fact not in seen:
                seen.add(fact)
                unique.append(fact)
        return tuple(unique)
