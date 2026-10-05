"""LangChain's ``SummarizationMiddleware``, run once ContextSage decides to."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from langchain.agents.middleware.summarization import SummarizationMiddleware
from langchain_core.messages import RemoveMessage
from langgraph.runtime import Runtime

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from langchain.agents.middleware.types import AgentState
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import BaseMessage, MessageLikeRepresentation

    from contextsage._pipeline.budget import Window

type TokenCounter = Callable[[Iterable[MessageLikeRepresentation]], int]

_ALWAYS = ("tokens", 1)
"""The wrapped middleware's trigger: ContextSage has already decided to run."""


class Summarizer:
    """Delegates semantic summarization to LangChain.

    LangChain owns where the history is cut (honoring ``keep`` and never
    splitting a tool call from its results) and the summary model call,
    including its retries. ContextSage only decides when this runs, and
    validates the arguments before they get here.

    Args:
        model: The chat model that writes summaries.
        keep: The window that stays verbatim, in messages or tokens.
        token_counter: Token counter, or ``None`` for LangChain's default.
        summary_prompt: Prompt template with a ``{messages}`` placeholder, or
            ``None`` for LangChain's default.
        trim_tokens_to_summarize: Token budget for the summary call's input,
            or ``None`` for no trimming.
    """

    def __init__(
        self,
        model: BaseChatModel,
        *,
        keep: Window,
        token_counter: TokenCounter | None,
        summary_prompt: str | None,
        trim_tokens_to_summarize: int | None,
    ) -> None:
        options: dict[str, Any] = {
            "trigger": _ALWAYS,
            "keep": keep,
            "trim_tokens_to_summarize": trim_tokens_to_summarize,
        }
        if token_counter is not None:
            options["token_counter"] = token_counter
        if summary_prompt is not None:
            options["summary_prompt"] = summary_prompt
        self._middleware = SummarizationMiddleware(model, **options)

    @property
    def token_counter(self) -> TokenCounter:
        """The token counter shared with LangChain's cutoff logic."""
        return self._middleware.token_counter

    @staticmethod
    def _state(messages: list[BaseMessage]) -> AgentState[Any]:
        return cast("AgentState[Any]", {"messages": messages})

    @staticmethod
    def _content(update: dict[str, Any] | None) -> list[BaseMessage] | None:
        if update is None:
            return None
        return [
            message
            for message in update["messages"]
            if not isinstance(message, RemoveMessage)
        ]

    def summarize(
        self, messages: list[BaseMessage], runtime: Runtime[Any] | None
    ) -> list[BaseMessage] | None:
        """Summarize synchronously.

        Returns:
            The summary followed by the kept messages, or ``None`` when there
            is nothing old enough to summarize.
        """
        return self._content(
            self._middleware.before_model(self._state(messages), runtime or Runtime())
        )

    async def asummarize(
        self, messages: list[BaseMessage], runtime: Runtime[Any] | None
    ) -> list[BaseMessage] | None:
        """Summarize asynchronously; see `summarize`."""
        return self._content(
            await self._middleware.abefore_model(
                self._state(messages), runtime or Runtime()
            )
        )
