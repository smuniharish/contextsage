"""LangGraph summarization adapter.

ContextSage never reimplements LLM-based semantic summarization.
This adapter wraps LangChain's own
``langchain.agents.middleware.summarization.SummarizationMiddleware`` and
invokes its ``before_model``/``abefore_model`` hooks directly against a
*prepared* message list that ContextSage has already decomposed, scored, and
selectively transformed.

Design note: the wrapped middleware is configured with a trigger that is
effectively "always eligible" (``("tokens", 0)``); ContextSage's own
:class:`~contextsage.budget.analyzer.BudgetAnalyzer` and
:class:`~contextsage.planning.planner.SummarizationPlanner` are the sole
authority on *whether* summarization runs. LangGraph's
``SummarizationMiddleware`` still owns *how many* messages to keep (via
``keep``) and the actual LLM summary generation — this keeps that
ownership boundary intact.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from langchain.agents.middleware.summarization import (
    ContextSize,
    SummarizationMiddleware,
    TriggerClause,
)
from langgraph.runtime import Runtime

from contextsage.exceptions import SummarizationError

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AnyMessage, BaseMessage, MessageLikeRepresentation

_ALWAYS_TRIGGER: ContextSize = ("tokens", 1)
"""Effectively-always-eligible trigger.

ContextSage's own budget analyzer and planner are the authority on *whether*
summarization runs; this adapter only calls into the
wrapped middleware once that decision has already been made, so its
internal trigger just needs to not itself refuse to run. LangGraph
requires trigger thresholds to be strictly positive, hence ``1`` rather
than ``0``.
"""


class LangGraphSummarizationAdapter:
    """Thin adapter around LangChain's ``SummarizationMiddleware``."""

    def __init__(
        self,
        model: str | BaseChatModel,
        *,
        keep: ContextSize = ("messages", 20),
        token_counter: Callable[[Iterable[MessageLikeRepresentation]], int] | None = None,
        summary_prompt: str | None = None,
        trim_tokens_to_summarize: int | None = 4000,
    ) -> None:
        kwargs: dict[str, Any] = {
            "trigger": _ALWAYS_TRIGGER,
            "keep": keep,
            "trim_tokens_to_summarize": trim_tokens_to_summarize,
        }
        if token_counter is not None:
            kwargs["token_counter"] = token_counter
        if summary_prompt is not None:
            kwargs["summary_prompt"] = summary_prompt
        self._middleware = SummarizationMiddleware(model, **kwargs)

    @property
    def keep(self) -> ContextSize | TriggerClause:
        return self._middleware.keep

    def summarize(self, messages: list[BaseMessage]) -> dict[str, Any] | None:
        """Invoke LangGraph's summarization synchronously over prepared messages."""
        try:
            state = {"messages": cast("list[AnyMessage]", messages)}
            return self._middleware.before_model(state, Runtime())
        except Exception as exc:
            raise SummarizationError(f"LangGraph summarization failed: {exc}") from exc

    async def asummarize(self, messages: list[BaseMessage]) -> dict[str, Any] | None:
        """Invoke LangGraph's summarization asynchronously over prepared messages."""
        try:
            state = {"messages": cast("list[AnyMessage]", messages)}
            return await self._middleware.abefore_model(state, Runtime())
        except Exception as exc:
            raise SummarizationError(f"LangGraph summarization failed: {exc}") from exc
