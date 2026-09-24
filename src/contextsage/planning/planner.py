"""Summarization planner — the core intelligence of ContextSage.

The planner does not decide "oldest messages first". It consumes already
classified context units (importance + preservation assigned upstream by
the importance/relationship/preservation engines) plus an explicit budget
report, and answers every question this decision requires: why is
summarization needed, what is a safe deterministic transformation target,
what must remain untouched, and what literal facts validation must later
confirm survived.
"""

from __future__ import annotations

from contextsage.core.models import (
    ContextUnit,
    PlanTarget,
    PreservationLevel,
    RegionKind,
    SummarizationPlan,
)

_DETERMINISTICALLY_COMPRESSIBLE_KINDS = frozenset(
    {RegionKind.LOG, RegionKind.JSON, RegionKind.TABLE, RegionKind.METADATA}
)
_COMPRESSIBLE_LEVELS = frozenset(
    {
        PreservationLevel.COMPRESSIBLE,
        PreservationLevel.REDUNDANT,
        PreservationLevel.SAFE_TO_DROP,
    }
)


class SummarizationPlanner:
    """Builds a :class:`SummarizationPlan` from classified context units."""

    def plan(
        self,
        units: list[ContextUnit],
        *,
        required: bool,
        trigger_reason: str,
        overflow_tokens: int,
        must_preserve_facts: tuple[str, ...],
        protected_message_ids: tuple[str, ...] = (),
    ) -> SummarizationPlan:
        if not required:
            return SummarizationPlan(
                required=False,
                trigger_reason=trigger_reason,
                overflow_tokens=0,
                protected_message_ids=protected_message_ids,
            )

        must_preserve_ids = tuple(
            u.unit_id for u in units if u.preservation is PreservationLevel.MUST_PRESERVE
        )

        deterministic_ids: list[str] = []
        preserve_ids: list[str] = []
        semantic_ids: list[str] = []
        for unit in units:
            if unit.message_id in protected_message_ids:
                preserve_ids.append(unit.unit_id)
                continue
            if unit.preservation in (
                PreservationLevel.MUST_PRESERVE,
                PreservationLevel.SHOULD_PRESERVE,
            ):
                preserve_ids.append(unit.unit_id)
            elif (
                unit.signals.kind in _DETERMINISTICALLY_COMPRESSIBLE_KINDS
                and unit.preservation in _COMPRESSIBLE_LEVELS
            ):
                deterministic_ids.append(unit.unit_id)
            else:
                semantic_ids.append(unit.unit_id)

        by_id = {u.unit_id: u for u in units}
        targets: list[PlanTarget] = []
        if deterministic_ids:
            savings = sum(by_id[i].token_count for i in deterministic_ids) // 2
            targets.append(
                PlanTarget(
                    unit_ids=tuple(deterministic_ids),
                    action="transform_deterministic",
                    reason=(
                        "structured/log/table content with compressible or redundant "
                        "preservation level can be safely reduced deterministically"
                    ),
                    estimated_token_savings=savings,
                )
            )
        if semantic_ids:
            targets.append(
                PlanTarget(
                    unit_ids=tuple(semantic_ids),
                    action="semantic_summarize",
                    reason="natural language content best compressed by an LLM",
                )
            )
        if preserve_ids:
            targets.append(
                PlanTarget(
                    unit_ids=tuple(preserve_ids),
                    action="preserve_untouched",
                    reason="must/should-preserve content or tool-call-paired message",
                )
            )

        return SummarizationPlan(
            required=True,
            trigger_reason=trigger_reason,
            overflow_tokens=overflow_tokens,
            targets=tuple(targets),
            must_preserve_unit_ids=must_preserve_ids,
            must_preserve_facts=must_preserve_facts,
            protected_message_ids=protected_message_ids,
        )
