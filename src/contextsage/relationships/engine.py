"""Relationship / dependency engine and tool-call pairing.

Two concerns live here:

1. **Tool-call pairing** (:func:`pair_tool_calls`) operates at the *message*
   level (not the unit level) because an ``AIMessage`` with ``tool_calls``
   must stay paired with its corresponding ``ToolMessage`` results — this is
   one of ContextSage's hard invariants. Reconstruction and
   validation both consult this pairing to guarantee no orphaned tool
   message ever appears in the rebuilt history.

2. **Unit-level relationships** (:class:`RelationshipEngine`) detects
   contradictions between conflicting facts, and links user corrections
   back to the values they correct, so summarization never silently
   collapses either into a false single certainty.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from contextsage.core.models import ContextUnit, Relationship, RelationType

if TYPE_CHECKING:
    from collections.abc import Sequence

    from langchain_core.messages import BaseMessage

_KEY_VALUE_RE = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]{2,30})\s*[:=]\s*([\"']?)(\w[\w.\-]*)\2")
_CORRECTION_REFERENT_RE = re.compile(
    r"(?:instead of|not)\s+([\w.\-]+)|use\s+([\w.\-]+)\s+instead", re.IGNORECASE
)
_MIN_DISTINCT_VALUES_FOR_CONTRADICTION = 2


def pair_tool_calls(messages: Sequence[BaseMessage]) -> dict[str, tuple[str | None, str | None]]:
    """Map each ``tool_call_id`` to ``(ai_message_id, tool_message_id)``.

    Used by the planner (to protect both sides together), the validator (to
    detect orphans), and the reconstructor (to guarantee valid pairing survives).
    """
    pairs: dict[str, tuple[str | None, str | None]] = {}
    for message in messages:
        tool_calls = getattr(message, "tool_calls", None) or []
        message_id = getattr(message, "id", None)
        for call in tool_calls:
            call_id = call.get("id") if isinstance(call, dict) else getattr(call, "id", None)
            if call_id:
                existing = pairs.get(call_id, (None, None))
                pairs[call_id] = (message_id, existing[1])
    for message in messages:
        tool_call_id = getattr(message, "tool_call_id", None)
        if tool_call_id:
            existing = pairs.get(tool_call_id, (None, None))
            pairs[tool_call_id] = (existing[0], getattr(message, "id", None))
    return pairs


class RelationshipEngine:
    """Detects contradictions and correction relationships between units."""

    def analyze(self, units: list[ContextUnit]) -> list[Relationship]:
        relationships: list[Relationship] = []
        relationships.extend(self._detect_contradictions(units))
        relationships.extend(self._detect_corrections(units))
        return relationships

    @staticmethod
    def _detect_contradictions(units: list[ContextUnit]) -> list[Relationship]:
        by_key: dict[str, list[tuple[ContextUnit, str]]] = {}
        for unit in units:
            for match in _KEY_VALUE_RE.finditer(unit.content):
                key, _, value = match.groups()
                by_key.setdefault(key.lower(), []).append((unit, value.lower()))

        relationships: list[Relationship] = []
        for key, occurrences in by_key.items():
            distinct_values = {value for _, value in occurrences}
            if len(distinct_values) < _MIN_DISTINCT_VALUES_FOR_CONTRADICTION:
                continue
            # Only flag genuine conflicts: different units asserting different
            # values for the same key (e.g. status=SUCCESS vs status=FAILED).
            first_by_value: dict[str, ContextUnit] = {}
            for unit, value in occurrences:
                first_by_value.setdefault(value, unit)
            values = list(first_by_value.items())
            for i in range(len(values)):
                for j in range(i + 1, len(values)):
                    (val_a, unit_a), (val_b, unit_b) = values[i], values[j]
                    relationships.append(
                        Relationship(
                            source_unit_id=unit_a.unit_id,
                            target_unit_id=unit_b.unit_id,
                            relation=RelationType.CONTRADICTS,
                            metadata={"key": key, "value_a": val_a, "value_b": val_b},
                        )
                    )
        return relationships

    @staticmethod
    def _detect_corrections(units: list[ContextUnit]) -> list[Relationship]:
        relationships: list[Relationship] = []
        for unit in units:
            if unit.importance is None or "user_correction" not in unit.importance.reasons:
                continue
            match = _CORRECTION_REFERENT_RE.search(unit.content)
            if not match:
                continue
            referent = next(g for g in match.groups() if g)
            for earlier in units:
                if earlier.message_index >= unit.message_index:
                    continue
                if referent.lower() in earlier.content.lower():
                    relationships.append(
                        Relationship(
                            source_unit_id=unit.unit_id,
                            target_unit_id=earlier.unit_id,
                            relation=RelationType.CORRECTED_BY,
                            metadata={"referent": referent},
                        )
                    )
        return relationships
