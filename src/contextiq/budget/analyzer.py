"""Context budget analysis.

The :class:`BudgetAnalyzer` computes an explicit, auditable accounting of
the model's context window: how many tokens are already spoken for by the
system prompt, tool schemas, reserved output, and safety margin, and
therefore how many tokens are actually available for conversation input.

ContextIQ never assumes "characters / 4" is an authoritative token count; it
delegates to a :class:`~contextiq.budget.tokens.TokenCounter` and clearly
tracks whether the resulting numbers are estimates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from contextiq.budget.tokens import TokenCounter
from contextiq.core.models import BudgetReport
from contextiq.exceptions import BudgetError

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from langchain_core.messages import BaseMessage

_DEFAULT_MAX_CONTEXT_TOKENS = 128_000
_DEFAULT_SAFETY_MARGIN_FRACTION = 0.10
_DEFAULT_SUMMARIZATION_OVERHEAD_TOKENS = 2_000


@dataclass(slots=True)
class BudgetConfig:
    """User/derived configuration for budget analysis."""

    maximum_context_tokens: int = _DEFAULT_MAX_CONTEXT_TOKENS
    reserved_output_tokens: int = 4_000
    safety_margin_fraction: float = _DEFAULT_SAFETY_MARGIN_FRACTION
    summarization_overhead_tokens: int = _DEFAULT_SUMMARIZATION_OVERHEAD_TOKENS

    def __post_init__(self) -> None:
        if self.maximum_context_tokens <= 0:
            raise BudgetError("maximum_context_tokens must be positive")
        if not 0.0 <= self.safety_margin_fraction < 1.0:
            raise BudgetError("safety_margin_fraction must be in [0, 1)")
        if self.reserved_output_tokens < 0:
            raise BudgetError("reserved_output_tokens must not be negative")


class BudgetAnalyzer:
    """Computes a :class:`BudgetReport` for a given message list."""

    def __init__(self, token_counter: TokenCounter, config: BudgetConfig | None = None) -> None:
        self._token_counter = token_counter
        self._config = config or BudgetConfig()

    def analyze(
        self,
        messages: Sequence[BaseMessage],
        *,
        system_prompt: str | None = None,
        tool_schemas: Iterable[str] = (),
    ) -> BudgetReport:
        try:
            current_input_tokens = self._token_counter.count_messages(messages)
            system_tokens = self._token_counter.count_text(system_prompt) if system_prompt else 0
            tool_schema_tokens = sum(
                self._token_counter.count_text(schema) for schema in tool_schemas
            )
        except Exception as exc:
            raise BudgetError(f"failed to compute budget: {exc}") from exc

        safety_margin_tokens = round(
            self._config.maximum_context_tokens * self._config.safety_margin_fraction
        )

        return BudgetReport(
            maximum_context_tokens=self._config.maximum_context_tokens,
            reserved_output_tokens=self._config.reserved_output_tokens,
            system_tokens=system_tokens,
            tool_schema_tokens=tool_schema_tokens,
            current_input_tokens=current_input_tokens,
            safety_margin_tokens=safety_margin_tokens,
            summarization_overhead_tokens=self._config.summarization_overhead_tokens,
        )


def infer_max_context_tokens(model: object, default: int = _DEFAULT_MAX_CONTEXT_TOKENS) -> int:
    """Best-effort extraction of a model's max input tokens from its profile.

    Falls back to ``default`` when the model exposes no profile information;
    this mirrors LangGraph's own graceful-degradation approach for models
    without published context-window metadata.
    """
    profile = getattr(model, "profile", None)
    if isinstance(profile, dict):
        value = profile.get("max_input_tokens")
        if isinstance(value, int) and value > 0:
            return value
    return default
