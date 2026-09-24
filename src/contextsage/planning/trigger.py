"""Trigger evaluation: deciding *whether* summarization is required.

ContextSage owns this decision, not the wrapped LangGraph
``SummarizationMiddleware``. It supports the same ``ContextSize`` trigger
vocabulary LangGraph uses (``("tokens", n)``, ``("messages", n)``,
``("fraction", f)``) for familiarity, evaluated against
ContextSage's own token counter and :class:`~contextsage.core.models.BudgetReport`.

When no trigger is supplied, the explicit budget accounting from
:class:`~contextsage.budget.analyzer.BudgetAnalyzer` (available input tokens
after reserving output, system prompt, tool schemas, and safety margin) is
used directly — this is the "budget-aware" default path.
"""

from __future__ import annotations

from dataclasses import dataclass

from contextsage.core.models import BudgetReport
from contextsage.exceptions import PlanningError

TriggerSpec = tuple[str, int | float] | None


@dataclass(slots=True)
class TriggerDecision:
    required: bool
    reason: str
    overflow_tokens: int


def evaluate_trigger(
    trigger: TriggerSpec,
    *,
    budget: BudgetReport,
    message_count: int,
) -> TriggerDecision:
    """Evaluate whether summarization should run.

    Only single ``(kind, value)`` trigger tuples are supported directly;
    this covers the primary documented usage
    (``trigger=("tokens", 100_000)``). Composite AND/OR trigger clauses are
    a LangGraph-level feature and are intentionally out of scope here — see
    ``docs/migration.md`` for the documented limitation.
    """
    if trigger is None:
        overflow = budget.overflow_tokens
        if overflow > 0:
            return TriggerDecision(
                required=True,
                reason=f"budget overflow of {overflow} tokens",
                overflow_tokens=overflow,
            )
        return TriggerDecision(required=False, reason="within configured budget", overflow_tokens=0)

    kind, value = trigger
    if kind == "tokens":
        overflow = max(budget.current_input_tokens - int(value), 0)
        required = budget.current_input_tokens >= value
        reason = f"input tokens ({budget.current_input_tokens}) reached trigger threshold ({value})"
    elif kind == "messages":
        required = message_count >= value
        overflow = budget.overflow_tokens if required else 0
        reason = f"message count ({message_count}) reached trigger threshold ({value})"
    elif kind == "fraction":
        threshold_tokens = round(budget.maximum_context_tokens * float(value))
        overflow = max(budget.current_input_tokens - threshold_tokens, 0)
        required = budget.current_input_tokens >= threshold_tokens
        reason = (
            f"input tokens ({budget.current_input_tokens}) reached "
            f"{value:.0%} of max context ({threshold_tokens})"
        )
    else:
        raise PlanningError(f"unsupported trigger kind: {kind!r}")

    if not required:
        reason = "within configured trigger threshold"
    return TriggerDecision(required=required, reason=reason, overflow_tokens=overflow)
