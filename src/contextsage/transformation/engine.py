"""Context transformation engine.

For every unit the planner has marked ``transform_deterministic``, this
engine asks: *can this be safely reduced deterministically?* If yes, it
applies a targeted, kind-specific transformation. If no — or if the
transformation raises — the unit is left completely untouched (fail-safe
behavior: optional structural processing failure must never
corrupt content).

A single large mixed-content message may have some units transformed here
(logs, JSON) and others left for LangGraph's semantic summarization
(ordinary natural language) — this keeps deterministic reduction and
semantic summarization cleanly separated.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from contextsage.core.models import RegionKind
from contextsage.exceptions import TransformationError
from contextsage.transformation.logs import reduce_log_block
from contextsage.transformation.structured import compact_json

if TYPE_CHECKING:
    from collections.abc import Callable

    from contextsage.budget.tokens import TokenCounter
    from contextsage.core.models import ContextUnit, SummarizationPlan

_TRANSFORMERS: dict[str, Callable[[str], str]] = {
    RegionKind.LOG.value: reduce_log_block,
    RegionKind.JSON.value: compact_json,
}


@dataclass(slots=True)
class TransformationOutcome:
    """Result of running the transformation engine over a plan."""

    units: tuple[ContextUnit, ...]
    transformed_unit_ids: tuple[str, ...]
    failed_unit_ids: tuple[str, ...]
    tokens_saved: int


class ContextTransformationEngine:
    """Applies safe, selective, per-unit deterministic transformations."""

    def __init__(self, token_counter: TokenCounter) -> None:
        self._token_counter = token_counter

    def transform(self, units: list[ContextUnit], plan: SummarizationPlan) -> TransformationOutcome:
        deterministic_ids: set[str] = set()
        for target in plan.targets:
            if target.action == "transform_deterministic":
                deterministic_ids.update(target.unit_ids)

        result_units: list[ContextUnit] = []
        transformed: list[str] = []
        failed: list[str] = []
        tokens_saved = 0

        for unit in units:
            if unit.unit_id not in deterministic_ids:
                result_units.append(unit)
                continue

            transformer = _TRANSFORMERS.get(str(unit.signals.kind))
            if transformer is None:
                result_units.append(unit)
                continue

            try:
                new_content = transformer(unit.content)
            except TransformationError:
                # Fail-safe: leave the unit exactly as it was.
                result_units.append(unit)
                failed.append(unit.unit_id)
                continue

            if len(new_content) >= len(unit.content):
                # Transformation produced no real reduction; not worth the risk
                # of altering content, so keep the original.
                result_units.append(unit)
                continue

            new_token_count = self._token_counter.count_text(new_content)
            tokens_saved += max(unit.token_count - new_token_count, 0)
            result_units.append(
                replace(
                    unit,
                    content=new_content,
                    token_count=new_token_count,
                    metadata={**unit.metadata, "contextsage_transformed": True},
                )
            )
            transformed.append(unit.unit_id)

        return TransformationOutcome(
            units=tuple(result_units),
            transformed_unit_ids=tuple(transformed),
            failed_unit_ids=tuple(failed),
            tokens_saved=tokens_saved,
        )
