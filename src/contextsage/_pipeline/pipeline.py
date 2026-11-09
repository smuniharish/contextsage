"""Analysis and deterministic compaction of a history before summarization."""

from __future__ import annotations

from typing import TYPE_CHECKING

from contextsage._pipeline.importance import score
from contextsage._pipeline.lineage import carried_facts
from contextsage._pipeline.models import Analysis, Prepared
from contextsage._pipeline.preservation import classify, extract_facts
from contextsage._pipeline.reconstruction import rebuild
from contextsage._pipeline.relationships import find_contradictions
from contextsage._pipeline.transformation import compact, plan

if TYPE_CHECKING:
    from collections.abc import Sequence

    from contextsage._pipeline.decomposition import Decomposer
    from contextsage.contracts import PreservationPolicy
    from contextsage.messages import Message


class Pipeline:
    """Decomposes, scores and compacts a history.

    Args:
        decomposer: Splits messages into content units.
        policy: The preservation policy.
    """

    def __init__(self, decomposer: Decomposer, policy: PreservationPolicy) -> None:
        self._decomposer = decomposer
        self._policy = policy

    async def prepare(self, messages: Sequence[Message]) -> Prepared:
        """Analyze the history and compact what can be compacted safely.

        Args:
            messages: The full history.

        Returns:
            The compacted history and its analysis.
        """
        units = await self._decomposer.decompose(messages)
        importance = score(units)
        contradictions = find_contradictions(units)
        preservation = classify(units, importance, contradictions, self._policy)
        facts = extract_facts(
            units,
            importance,
            preservation,
            contradictions,
            carried=carried_facts(messages),
        )
        mode = self._policy.json_compaction
        replacements = {
            unit.unit_id: text
            for unit, lossy in plan(units, preservation, messages)
            if (text := compact(unit, mode=mode, lossy=lossy)) is not None
        }
        return Prepared(
            messages=rebuild(messages, units, replacements),
            analysis=Analysis(
                units=units,
                importance=importance,
                preservation=preservation,
                contradictions=contradictions,
                facts=facts,
            ),
            compacted_units=len(replacements),
        )
