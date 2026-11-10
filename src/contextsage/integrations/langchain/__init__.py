"""LangChain and LangGraph integration.

Requires ``pip install "contextsage[langchain]"``.

* `IntelligentSummarizationMiddleware` is a drop-in replacement for
  LangChain's ``SummarizationMiddleware`` for ``create_agent`` and Deep Agents.
* `LangChainAdapter` converts LangChain messages to and from
  `contextsage.Message`.
* `LangChainSummaryModel` lets a LangChain chat model write summaries.
* `LangChainTokenCounter` counts tokens with a LangChain counting function.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, override

from parsefabric import LanguageModel

from contextsage._pipeline.budget import DEFAULT_MAXIMUM_CONTEXT_TOKENS
from contextsage._pipeline.summary import DEFAULT_SUMMARY_PROMPT
from contextsage.contracts import FrameworkAdapter, TokenCounter
from contextsage.engine import ContextSummarizer
from contextsage.errors import ConfigurationError
from contextsage.messages import Message, SummaryLineage, ToolCall

try:
    from langchain.agents.middleware.internal_call_transformer import (
        InternalCallTransformer,
        internal_call_metadata,
    )
    from langchain.agents.middleware.types import AgentMiddleware, AgentState
    from langchain.chat_models import init_chat_model
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import (
        AIMessage,
        BaseMessage,
        HumanMessage,
        RemoveMessage,
        SystemMessage,
        ToolMessage,
    )
    from langchain_core.messages.utils import count_tokens_approximately
    from langgraph.errors import GraphBubbleUp
    from langgraph.graph.message import REMOVE_ALL_MESSAGES
except ImportError as error:  # pragma: no cover - requires an environment without the extra
    raise ImportError(
        'contextsage.integrations.langchain requires: pip install "contextsage[langchain]"'
    ) from error

if TYPE_CHECKING:
    import re
    from collections.abc import Callable, Coroutine, Sequence

    from agxai import ProvenanceLink, XAIRuntime
    from langgraph.runtime import Runtime
    from parsefabric import ChatMessage

    from contextsage.contracts import EventSink, PreservationPolicy
    from contextsage.engine import ContextSize, SummarizationResult, TriggerSpec
    from contextsage.messages import Role
    from contextsage.parsing import ParsingOptions

__all__ = [
    "LINEAGE_KEY",
    "IntelligentSummarizationMiddleware",
    "LangChainAdapter",
    "LangChainSummaryModel",
    "LangChainTokenCounter",
]

LINEAGE_KEY = "contextsage"
"""Key of the lineage record in a summary message's ``additional_kwargs``."""

_SUMMARY_SOURCE = "summarization"
_CHAT_ROLES: Mapping[str, Role] = {
    "system": "system",
    "developer": "system",
    "user": "user",
    "human": "user",
    "assistant": "assistant",
    "ai": "assistant",
    "tool": "tool",
}


class LangChainAdapter(FrameworkAdapter[BaseMessage]):
    """Converts LangChain messages to and from `contextsage.Message`.

    Summaries are ``HumanMessage`` objects marked with
    ``additional_kwargs={"lc_source": "summarization"}``, with the lineage
    record under ``additional_kwargs["contextsage"]``. Messages whose content
    is not plain text, such as image blocks, are never rewritten.
    """

    @property
    @override
    def propagated_errors(self) -> tuple[type[BaseException], ...]:
        return (GraphBubbleUp,)

    @override
    def to_message(self, native: BaseMessage) -> Message:
        kwargs = native.additional_kwargs
        lineage = None
        if LINEAGE_KEY in kwargs:
            lineage = SummaryLineage.from_dict(kwargs[LINEAGE_KEY], summary_id=native.id or "")
        tool_calls: tuple[ToolCall, ...] = ()
        if isinstance(native, AIMessage):
            tool_calls = tuple(
                ToolCall(call.get("id") or "", call["name"], dict(call["args"]))
                for call in native.tool_calls
            )
        return Message(
            _role(native),
            native.text,
            id=native.id,
            name=native.name,
            tool_calls=tool_calls,
            tool_call_id=native.tool_call_id if isinstance(native, ToolMessage) else None,
            rewritable=isinstance(native.content, str),
            lineage=lineage,
            native=native,
        )

    @override
    def from_message(self, message: Message) -> BaseMessage:
        native = message.native
        if isinstance(native, BaseMessage):
            if self.to_message(native) == message:
                return native
            update: dict[str, Any] = {"content": message.content}
            if message.lineage is not None:
                update["additional_kwargs"] = _summary_kwargs(
                    native.additional_kwargs, message.lineage
                )
            return native.model_copy(update=update)
        if message.lineage is not None:
            return HumanMessage(
                content=message.content,
                id=message.id,
                name=message.name,
                additional_kwargs=_summary_kwargs({}, message.lineage),
            )
        return _new_message(message)


def _role(native: BaseMessage) -> Role:
    role = getattr(native, "role", None)
    if isinstance(role, str) and role in _CHAT_ROLES:
        return _CHAT_ROLES[role]
    return _CHAT_ROLES.get(native.type, "user")


def _summary_kwargs(kwargs: Mapping[str, Any], lineage: SummaryLineage) -> dict[str, Any]:
    return {**kwargs, "lc_source": _SUMMARY_SOURCE, LINEAGE_KEY: lineage.to_dict()}


def _new_message(message: Message) -> BaseMessage:
    match message.role:
        case "system":
            return SystemMessage(content=message.content, id=message.id, name=message.name)
        case "assistant":
            return AIMessage(
                content=message.content,
                id=message.id,
                name=message.name,
                tool_calls=[
                    {
                        "id": call.id,
                        "name": call.name,
                        "args": dict(call.arguments),
                        "type": "tool_call",
                    }
                    for call in message.tool_calls
                ],
            )
        case "tool":
            return ToolMessage(
                content=message.content,
                id=message.id,
                name=message.name,
                tool_call_id=message.tool_call_id or "",
            )
        case _:
            return HumanMessage(content=message.content, id=message.id, name=message.name)


class LangChainSummaryModel(LanguageModel):
    """A `parsefabric.LanguageModel` backed by a LangChain chat model.

    Summary calls are tagged with ``lc_source="summarization"`` and
    LangChain's internal-call metadata, so their tokens never appear in the
    agent's streamed messages.

    Args:
        model: A LangChain chat model, or an ``init_chat_model`` identifier
            such as ``"openai:gpt-5-mini"``.

    Raises:
        ConfigurationError: If the model cannot be initialized.
    """

    def __init__(self, model: str | BaseChatModel) -> None:
        if isinstance(model, str):
            try:
                model = init_chat_model(model)
            except Exception as error:
                raise ConfigurationError(f"cannot initialize model: {error}") from error
        if not isinstance(model, BaseChatModel):
            raise ConfigurationError("model must be a LangChain BaseChatModel or model identifier")
        self._model = model

    @property
    def model(self) -> BaseChatModel:
        """The wrapped chat model."""
        return self._model

    @property
    @override
    def name(self) -> str:
        return f"langchain:{type(self._model).__name__}"

    @property
    def max_input_tokens(self) -> int | None:
        """The context window from the model's profile, if it declares one."""
        profile = getattr(self._model, "profile", None)
        if isinstance(profile, Mapping):
            value = profile.get("max_input_tokens")
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                return value
        return None

    @override
    async def complete(self, messages: Sequence[ChatMessage]) -> str:
        reply = await self._model.ainvoke(
            [_new_message(Message(message.role, message.content)) for message in messages],
            config={"metadata": {"lc_source": _SUMMARY_SOURCE, **internal_call_metadata()}},
        )
        return reply.text


class LangChainTokenCounter(TokenCounter):
    """Counts tokens with a LangChain message-counting function.

    Args:
        counter: Counts a list of LangChain messages. Defaults to
            ``count_tokens_approximately``.
        adapter: Converts messages to LangChain messages.
    """

    def __init__(
        self,
        counter: Callable[[Sequence[BaseMessage]], int] = count_tokens_approximately,
        *,
        adapter: LangChainAdapter | None = None,
    ) -> None:
        if not callable(counter):
            raise ConfigurationError("counter must be callable")
        self._counter = counter
        self._adapter = adapter or LangChainAdapter()

    @override
    async def count(self, messages: Sequence[Message]) -> int:
        return self._counter(self._adapter.from_messages(messages))


class _LoopThread:
    """A private event loop in a daemon thread, for the synchronous hook."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def run[T](self, coroutine: Coroutine[Any, Any, T]) -> T:
        with self._lock:
            if self._loop is None:
                self._loop = asyncio.new_event_loop()
                threading.Thread(
                    target=self._serve, args=(self._loop,), name="contextsage", daemon=True
                ).start()
            loop = self._loop
        return asyncio.run_coroutine_threadsafe(coroutine, loop).result()

    @staticmethod
    def _serve(loop: asyncio.AbstractEventLoop) -> None:
        try:
            loop.run_forever()
        finally:
            loop.close()

    def close(self) -> None:
        with self._lock:
            loop, self._loop = self._loop, None
        if loop is not None:
            loop.call_soon_threadsafe(loop.stop)


def _runtime_ids(runtime: object) -> tuple[str | None, str | None]:
    info = getattr(runtime, "execution_info", None)
    server = getattr(runtime, "server_info", None)
    return getattr(info, "thread_id", None), getattr(server, "graph_id", None)


class IntelligentSummarizationMiddleware(AgentMiddleware[AgentState[Any], Any, Any]):
    """Information-aware replacement for LangChain's ``SummarizationMiddleware``.

    Before each model call, the middleware runs a `contextsage.ContextSummarizer`
    on the agent's messages and, when it rewrites them, replaces the history
    in the agent state. Provenance is scoped by the LangGraph thread ID.

    Example:
        ```python
        from langchain.agents import create_agent

        from contextsage.integrations.langchain import IntelligentSummarizationMiddleware

        agent = create_agent(
            model="openai:gpt-5",
            tools=tools,
            middleware=[
                IntelligentSummarizationMiddleware(
                    "openai:gpt-5-mini",
                    trigger=("tokens", 100_000),
                    keep=("messages", 20),
                )
            ],
        )
        ```

    Args:
        model: Chat model, or ``init_chat_model`` identifier, that writes
            summaries.
        maximum_context_tokens: The model's context window. Defaults to the
            model profile's ``max_input_tokens``, else 128,000.
        token_counter: Counts tokens. Defaults to `LangChainTokenCounter`.
        adapter: Converts LangChain messages. Defaults to `LangChainAdapter`.

    Every other argument is passed to `contextsage.ContextSummarizer`.

    Raises:
        ConfigurationError: If an argument is invalid or the model cannot be
            initialized.
    """

    transformers = (InternalCallTransformer,)
    """Keeps the summary model's tokens out of the agent's streamed messages."""

    def __init__(
        self,
        model: str | BaseChatModel,
        *,
        trigger: TriggerSpec | None = None,
        keep: ContextSize = ("messages", 20),
        policy: PreservationPolicy | None = None,
        maximum_context_tokens: int | None = None,
        reserved_output_tokens: int = 4_000,
        safety_margin: float = 0.10,
        summarization_overhead_tokens: int = 2_000,
        token_counter: TokenCounter | None = None,
        identifier_patterns: Sequence[re.Pattern[str]] | None = None,
        validation_enabled: bool = True,
        summary_prompt: str = DEFAULT_SUMMARY_PROMPT,
        trim_tokens_to_summarize: int | None = 4_000,
        parsing: ParsingOptions | None = None,
        sink: EventSink | None = None,
        runtime: XAIRuntime | None = None,
        adapter: LangChainAdapter | None = None,
    ) -> None:
        super().__init__()
        if adapter is not None and not isinstance(adapter, LangChainAdapter):
            raise ConfigurationError("adapter must be a LangChainAdapter")
        self._adapter = adapter or LangChainAdapter()
        summary_model = LangChainSummaryModel(model)
        self._summarizer = ContextSummarizer(
            summary_model,
            trigger=trigger,
            keep=keep,
            policy=policy,
            maximum_context_tokens=maximum_context_tokens
            or summary_model.max_input_tokens
            or DEFAULT_MAXIMUM_CONTEXT_TOKENS,
            reserved_output_tokens=reserved_output_tokens,
            safety_margin=safety_margin,
            summarization_overhead_tokens=summarization_overhead_tokens,
            token_counter=token_counter or LangChainTokenCounter(adapter=self._adapter),
            identifier_patterns=identifier_patterns,
            validation_enabled=validation_enabled,
            summary_prompt=summary_prompt,
            trim_tokens_to_summarize=trim_tokens_to_summarize,
            parsing=parsing,
            sink=sink,
            runtime=runtime,
            propagate_errors=self._adapter.propagated_errors,
        )
        self._loop = _LoopThread()

    @property
    def summarizer(self) -> ContextSummarizer:
        """The engine that rewrites the history."""
        return self._summarizer

    async def alineage(
        self, summary_id: str, *, thread_id: str | None = None
    ) -> tuple[ProvenanceLink, ...]:
        """Return the provenance of a summary; see `contextsage.ContextSummarizer.lineage`."""
        return await self._summarizer.lineage(summary_id, thread_id=thread_id)

    async def adelete_lineage(self, *, thread_id: str | None = None) -> int:
        """Delete a thread's provenance; see `contextsage.ContextSummarizer.delete_lineage`."""
        return await self._summarizer.delete_lineage(thread_id=thread_id)

    async def aclose(self) -> None:
        """Release the summarizer's resources; see `contextsage.ContextSummarizer.aclose`.

        Also stops the event loop thread used by the synchronous hook.
        """
        try:
            await self._summarizer.aclose()
        finally:
            self._loop.close()

    @override
    async def abefore_model(
        self, state: AgentState[Any], runtime: Runtime[Any]
    ) -> dict[str, Any] | None:
        """Summarize the history before a model call when the trigger fires.

        Returns:
            A state update replacing the history, or ``None`` to leave it.
        """
        thread_id, graph_id = _runtime_ids(runtime)
        result = await self._summarizer.summarize(
            self._adapter.to_messages(state["messages"]), thread_id=thread_id, graph_id=graph_id
        )
        return None if result is None else self._update(result)

    @override
    def before_model(self, state: AgentState[Any], runtime: Runtime[Any]) -> dict[str, Any] | None:
        """Synchronous counterpart of `abefore_model`, for ``agent.invoke``.

        The work runs on a private event loop thread; prefer ``agent.ainvoke``.
        """
        return self._loop.run(self.abefore_model(state, runtime))

    def _update(self, result: SummarizationResult) -> dict[str, Any]:
        return {
            "messages": [
                RemoveMessage(id=REMOVE_ALL_MESSAGES),
                *self._adapter.from_messages(result.messages),
            ]
        }
