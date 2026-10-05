"""`IntelligentSummarizationMiddleware`: information-aware summarization for agents."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from langchain.agents.middleware.internal_call_transformer import (
    InternalCallTransformer,
)
from langchain.agents.middleware.types import AgentMiddleware, AgentState
from langchain.chat_models import init_chat_model
from langchain_core.messages import RemoveMessage
from langgraph.errors import GraphBubbleUp
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph_xai import InMemoryProvenanceStore
from parsefabric.builtins import DEFAULT_CODE_LANGUAGES

from contextsage._pipeline._sync import run_sync
from contextsage._pipeline.budget import (
    Budget,
    Trigger,
    resolve_keep,
    resolve_maximum_context_tokens,
)
from contextsage._pipeline.lineage import new_summary_id, replaced_summaries, stamp
from contextsage._pipeline.models import Analysis, Prepared
from contextsage._pipeline.parsing import build_parser
from contextsage._pipeline.pipeline import Pipeline
from contextsage._pipeline.preservation import POLICIES
from contextsage._pipeline.provenance import ProvenanceRecorder
from contextsage._pipeline.recovery import fallback, restate
from contextsage._pipeline.signals import DEFAULT_IDENTIFIER_PATTERNS
from contextsage._pipeline.summarizer import Summarizer
from contextsage._pipeline.validation import validate
from contextsage.errors import ConfigurationError
from contextsage.events import SummarizationEvent

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from langchain.agents.middleware.summarization import ContextSize, TriggerClause
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import BaseMessage
    from langgraph.runtime import Runtime
    from langgraph_xai import ProvenanceLink, ProvenanceStore
    from parsefabric import Parser
    from parsefabric.patterns import Pattern

    from contextsage._pipeline.budget import Decision
    from contextsage._pipeline.preservation import Policy
    from contextsage._pipeline.summarizer import TokenCounter
    from contextsage.events import RecoveryStatus, ValidationStatus

__all__ = ["IntelligentSummarizationMiddleware"]

logger = logging.getLogger("contextsage")

type TriggerSpec = ContextSize | TriggerClause | list[ContextSize | TriggerClause]


@dataclass(frozen=True, slots=True)
class _Run:
    started: float
    messages: list[BaseMessage]
    tokens: int
    decision: Decision


@dataclass(frozen=True, slots=True)
class _Outcome:
    messages: list[BaseMessage]
    summary_id: str | None
    generation: int
    source_ids: tuple[str, ...]
    validation_status: ValidationStatus
    recovery_status: RecoveryStatus


def _runtime_ids(runtime: Runtime[Any] | None) -> tuple[str | None, str | None]:
    info = getattr(runtime, "execution_info", None)
    server = getattr(runtime, "server_info", None)
    return getattr(info, "thread_id", None), getattr(server, "graph_id", None)


class IntelligentSummarizationMiddleware(AgentMiddleware[AgentState[Any], Any, Any]):
    """Information-aware replacement for LangChain's ``SummarizationMiddleware``.

    Before each model call, the middleware decides whether the history needs
    summarizing. When it does, it parses every message with parsefabric into
    content units (prose, JSON, logs, tables, code, stack traces), scores them,
    decides what must be preserved, and losslessly compacts low-value
    structured content. LangChain's ``SummarizationMiddleware`` then writes
    the summary. Finally the middleware verifies that every must-preserve fact
    survived, restates any that did not, and links the summarized messages to
    the summary in a langgraph-xai provenance store.

    Example:
        ```python
        from langchain.agents import create_agent

        from contextsage import IntelligentSummarizationMiddleware

        agent = create_agent(
            model="openai:gpt-5",
            tools=tools,
            middleware=[
                IntelligentSummarizationMiddleware(
                    model="openai:gpt-5-mini",
                    trigger=("tokens", 100_000),
                    keep=("messages", 20),
                )
            ],
        )
        ```

    Args:
        model: Chat model, or ``init_chat_model`` identifier, that writes
            summaries.
        trigger: When to summarize. Accepts LangChain's forms:
            ``("tokens", n)``, ``("messages", n)``, ``("fraction", f)``, a
            clause such as ``{"tokens": 4000, "messages": 10}`` whose
            conditions must all hold, or a list in which any item may hold.
            ``None`` (the default) summarizes when the history no longer fits
            the token budget described by the next four arguments.
        keep: How much recent history stays verbatim, as
            ``("messages", n)``, ``("tokens", n)`` or ``("fraction", f)``, a
            share of ``maximum_context_tokens``.
        policy: How readily content is compacted: ``"maximum_preservation"``,
            ``"balanced"`` or ``"maximum_compression"``.
        maximum_context_tokens: The model's context window. Defaults to the
            model profile's ``max_input_tokens``, else 128,000.
        reserved_output_tokens: Tokens kept free for the model's response.
        safety_margin: Fraction of the context window held back as a buffer.
        summarization_overhead_tokens: Tokens kept free for the system prompt,
            tool schemas and the summary call's own prompt.
        token_counter: Counts tokens in a list of messages, like LangChain's
            ``count_tokens_approximately``. Defaults to the counter LangChain's
            ``SummarizationMiddleware`` uses for the model, which is calibrated
            by the provider's reported usage.
        routes: Extra parsefabric ``(selector, parser)`` routes, tried before
            the built-in JSON route. A routed parser's name becomes the content
            kind of the lines it parses.
        fence_routes: parsefabric parsers for fenced code blocks, by language
            tag.
        code_languages: tree-sitter grammars used to recognize unfenced code.
            ``()`` disables code detection.
        identifier_patterns: Regular expressions for identifiers that must
            survive summarization. Replaces
            `contextsage.DEFAULT_IDENTIFIER_PATTERNS`, which match UUIDs,
            ``ABC-123`` keys, ``request_id=...`` assignments and phrases such
            as ``customer 456``; pass
            ``[*DEFAULT_IDENTIFIER_PATTERNS, re.compile(...)]`` to extend them.
        validation_enabled: Verify the rewritten history and restate missing
            facts.
        observability_hook: Called with a `contextsage.SummarizationEvent`
            each time the history is rewritten.
        provenance_store: langgraph-xai ``ProvenanceStore`` that receives a
            ``derived_from`` link from each summarized message to its summary.
            Defaults to an ``InMemoryProvenanceStore``, which keeps links until
            the process exits; use a durable store in production.
        summary_prompt: Prompt for the summary model, with a ``{messages}``
            placeholder. Defaults to LangChain's prompt.
        trim_tokens_to_summarize: Token budget for the messages sent to the
            summary model, or ``None`` to send them all.

    Raises:
        ConfigurationError: If an argument is invalid, the model cannot be
            initialized, or the code-detection grammars cannot be loaded.
    """

    transformers = (InternalCallTransformer,)
    """Keeps the summary model's tokens out of the agent's streamed messages."""

    def __init__(
        self,
        model: str | BaseChatModel,
        *,
        trigger: TriggerSpec | None = None,
        keep: ContextSize = ("messages", 20),
        policy: Policy = "balanced",
        maximum_context_tokens: int | None = None,
        reserved_output_tokens: int = 4_000,
        safety_margin: float = 0.10,
        summarization_overhead_tokens: int = 2_000,
        token_counter: TokenCounter | None = None,
        routes: Sequence[tuple[Pattern, Parser]] = (),
        fence_routes: Mapping[str, Parser] | None = None,
        code_languages: Sequence[str] = DEFAULT_CODE_LANGUAGES,
        identifier_patterns: Sequence[re.Pattern[str]] | None = None,
        validation_enabled: bool = True,
        observability_hook: Callable[[SummarizationEvent], None] | None = None,
        provenance_store: ProvenanceStore | None = None,
        summary_prompt: str | None = None,
        trim_tokens_to_summarize: int | None = 4_000,
    ) -> None:
        super().__init__()
        if policy not in POLICIES:
            raise ConfigurationError(f"policy must be one of {', '.join(POLICIES)}")
        if summary_prompt is not None and "{messages}" not in summary_prompt:
            raise ConfigurationError(
                "summary_prompt must contain a {messages} placeholder"
            )
        if trim_tokens_to_summarize is not None and (
            isinstance(trim_tokens_to_summarize, bool)
            or not isinstance(trim_tokens_to_summarize, int)
            or trim_tokens_to_summarize <= 0
        ):
            raise ConfigurationError(
                "trim_tokens_to_summarize must be a positive integer or None"
            )
        patterns = (
            DEFAULT_IDENTIFIER_PATTERNS
            if identifier_patterns is None
            else tuple(identifier_patterns)
        )
        if not all(
            isinstance(pattern, re.Pattern) and isinstance(pattern.pattern, str)
            for pattern in patterns
        ):
            raise ConfigurationError(
                "identifier_patterns must be compiled text regexes"
            )
        if observability_hook is not None and not callable(observability_hook):
            raise ConfigurationError("observability_hook must be callable")
        if isinstance(model, str):
            try:
                model = init_chat_model(model)
            except Exception as error:
                raise ConfigurationError(f"cannot initialize model: {error}") from error

        self._budget = Budget(
            maximum_context_tokens=resolve_maximum_context_tokens(
                model, maximum_context_tokens
            ),
            reserved_output_tokens=reserved_output_tokens,
            safety_margin=safety_margin,
            summarization_overhead_tokens=summarization_overhead_tokens,
        )
        self._keep = resolve_keep(keep, self._budget.maximum_context_tokens)
        self._summarizer = Summarizer(
            model,
            keep=self._keep,
            token_counter=token_counter,
            summary_prompt=summary_prompt,
            trim_tokens_to_summarize=trim_tokens_to_summarize,
        )
        self._trigger = Trigger(trigger, self._budget)
        self._pipeline = Pipeline(
            parser=build_parser(
                routes=routes, fence_routes=fence_routes, code_languages=code_languages
            ),
            identifier_patterns=patterns,
            policy=policy,
        )
        self._validation_enabled = validation_enabled
        self._hook = observability_hook
        self._provenance = ProvenanceRecorder(
            InMemoryProvenanceStore() if provenance_store is None else provenance_store
        )

    @property
    def provenance_store(self) -> ProvenanceStore:
        """The langgraph-xai store that receives provenance links."""
        return self._provenance.store

    async def alineage(
        self, summary_id: str, *, thread_id: str | None = None
    ) -> tuple[ProvenanceLink, ...]:
        """Return the provenance of a summary, nearest links first.

        Walks back from the summary through every earlier summary it replaced
        to the original messages.

        Args:
            summary_id: ID of a summary message (also reported as
                `contextsage.SummarizationEvent.summary_id`).
            thread_id: The LangGraph thread the summary belongs to; ``None``
                for agents that run without a checkpointer.

        Returns:
            The ``derived_from`` links, each from a source to what it became.
        """
        return await self._provenance.lineage(summary_id, thread_id)

    # -- agent hooks ---------------------------------------------------------

    def before_model(
        self, state: AgentState[Any], runtime: Runtime[Any]
    ) -> dict[str, Any] | None:
        """Summarize the history before a model call when the trigger fires.

        Args:
            state: The agent state.
            runtime: The LangGraph runtime.

        Returns:
            A state update replacing the history, or ``None`` to leave it.
        """
        run = self._begin(state)
        if run is None:
            return None
        try:
            prepared = self._prepare(run.messages)
        except Exception as error:
            prepared = self._unanalyzed(run, error)
        try:
            summarized = self._summarizer.summarize(prepared.messages, runtime)
        except GraphBubbleUp:
            raise
        except Exception as error:
            outcome = self._recover(prepared, error)
        else:
            outcome = self._finalize(prepared, summarized)
        if outcome is None:
            return None
        if outcome.summary_id is not None and outcome.source_ids:
            thread_id, graph_id = _runtime_ids(runtime)
            run_sync(
                self._provenance.record(
                    source_ids=outcome.source_ids,
                    summary_id=outcome.summary_id,
                    thread_id=thread_id,
                    graph_id=graph_id,
                )
            )
        return self._complete(run, prepared, outcome, runtime)

    async def abefore_model(
        self, state: AgentState[Any], runtime: Runtime[Any]
    ) -> dict[str, Any] | None:
        """Asynchronous counterpart of `before_model`.

        Analysis is CPU-bound, so it runs in a worker thread and never blocks
        the event loop.
        """
        run = self._begin(state)
        if run is None:
            return None
        try:
            prepared = await asyncio.to_thread(self._prepare, run.messages)
        except Exception as error:
            prepared = self._unanalyzed(run, error)
        try:
            summarized = await self._summarizer.asummarize(prepared.messages, runtime)
        except GraphBubbleUp:
            raise
        except Exception as error:
            outcome = self._recover(prepared, error)
        else:
            outcome = self._finalize(prepared, summarized)
        if outcome is None:
            return None
        if outcome.summary_id is not None and outcome.source_ids:
            thread_id, graph_id = _runtime_ids(runtime)
            await self._provenance.record(
                source_ids=outcome.source_ids,
                summary_id=outcome.summary_id,
                thread_id=thread_id,
                graph_id=graph_id,
            )
        return self._complete(run, prepared, outcome, runtime)

    # -- shared steps --------------------------------------------------------

    def _begin(self, state: AgentState[Any]) -> _Run | None:
        started = time.perf_counter()
        messages: list[BaseMessage] = [*state["messages"]]
        tokens = self._summarizer.token_counter(messages)
        decision = self._trigger.evaluate(tokens=tokens, messages=len(messages))
        if decision is None:
            return None
        return _Run(started, messages, tokens, decision)

    def _prepare(self, messages: list[BaseMessage]) -> Prepared:
        """Analyze and compact the history; parsefabric's parsing is async."""
        return run_sync(self._pipeline.prepare(messages))

    @staticmethod
    def _unanalyzed(run: _Run, error: Exception) -> Prepared:
        """Fall back to plain LangChain summarization when analysis fails."""
        logger.error(
            "contextsage could not analyze the history; summarizing it unanalyzed",
            exc_info=error,
        )
        return Prepared(
            messages=list(run.messages),
            analysis=Analysis(
                units=(), importance={}, preservation={}, contradictions=(), facts=()
            ),
            compacted_units=0,
        )

    def _finalize(
        self, prepared: Prepared, summarized: list[BaseMessage] | None
    ) -> _Outcome | None:
        facts = prepared.analysis.facts
        if summarized is None:
            if not prepared.compacted_units:
                return None
            return _Outcome(
                messages=prepared.messages,
                summary_id=None,
                generation=0,
                source_ids=(),
                validation_status="passed" if self._validation_enabled else "disabled",
                recovery_status="none_needed",
            )
        kept_ids = {message.id for message in summarized if message.id}
        generation, replaced = replaced_summaries(prepared.messages, kept_ids)
        summary_id = new_summary_id()
        messages = [
            stamp(
                summarized[0],
                summary_id=summary_id,
                generation=generation,
                source_summary_ids=replaced,
                facts=facts,
            ),
            *summarized[1:],
        ]
        source_ids = tuple(
            message.id
            for message in prepared.messages
            if message.id and message.id not in kept_ids
        )
        validation_status: ValidationStatus = "disabled"
        recovery_status: RecoveryStatus = "none_needed"
        if self._validation_enabled:
            result = validate(messages, facts)
            validation_status = "passed"
            if result.missing:
                messages = restate(messages, result.missing)
                validation_status = "failed_recovered"
                recovery_status = "restated_facts"
            if result.orphaned_tool_results:
                logger.warning(
                    "contextsage found tool results without their tool call after "
                    "summarization: %s",
                    ", ".join(result.orphaned_tool_results),
                )
                validation_status = "failed_unrecovered"
                if not result.missing:
                    recovery_status = "none_applicable"
        return _Outcome(
            messages=messages,
            summary_id=summary_id,
            generation=generation,
            source_ids=source_ids,
            validation_status=validation_status,
            recovery_status=recovery_status,
        )

    def _recover(self, prepared: Prepared, error: Exception) -> _Outcome:
        logger.warning(
            "contextsage summary model failed (%s); trimming to the keep window",
            type(error).__name__,
            exc_info=error,
        )
        facts = prepared.analysis.facts
        messages, summary_index = fallback(
            prepared.messages,
            keep=self._keep,
            token_counter=self._summarizer.token_counter,
            facts=lambda window: validate(window, facts).missing,
        )
        kept_ids = {id(message) for message in messages}
        source_ids = tuple(
            message.id
            for message in prepared.messages
            if message.id and id(message) not in kept_ids
        )
        summary_id: str | None = None
        generation = 0
        if summary_index is not None:
            kept = {message.id for message in messages if message.id}
            generation, replaced = replaced_summaries(prepared.messages, kept)
            summary_id = new_summary_id()
            messages[summary_index] = stamp(
                messages[summary_index],
                summary_id=summary_id,
                generation=generation,
                source_summary_ids=replaced,
                facts=facts,
            )
        return _Outcome(
            messages=messages,
            summary_id=summary_id,
            generation=generation,
            source_ids=source_ids,
            validation_status="skipped",
            recovery_status="trimmed_fallback",
        )

    def _complete(
        self,
        run: _Run,
        prepared: Prepared,
        outcome: _Outcome,
        runtime: Runtime[Any] | None,
    ) -> dict[str, Any]:
        counter = self._summarizer.token_counter
        output_tokens = counter(outcome.messages)
        analysis = prepared.analysis
        event = SummarizationEvent(
            summary_id=outcome.summary_id,
            generation=outcome.generation,
            thread_id=_runtime_ids(runtime)[0],
            trigger_reason=run.decision.reason,
            input_messages=len(run.messages),
            input_tokens=run.tokens,
            available_tokens=self._budget.available_tokens,
            overflow_tokens=run.decision.overflow_tokens,
            prepared_tokens=counter(prepared.messages)
            if prepared.compacted_units
            else run.tokens,
            output_messages=len(outcome.messages),
            output_tokens=output_tokens,
            compression_ratio=output_tokens / run.tokens if run.tokens else 0.0,
            compacted_units=prepared.compacted_units,
            must_preserve_units=analysis.must_preserve_count,
            must_preserve_facts=len(analysis.facts),
            content_kinds=analysis.kind_counts(),
            validation_status=outcome.validation_status,
            recovery_status=outcome.recovery_status,
            latency_ms=(time.perf_counter() - run.started) * 1000,
        )
        logger.info("contextsage summarization", extra={"contextsage": event.as_dict()})
        if self._hook is not None:
            try:
                self._hook(event)
            except Exception:
                logger.warning("contextsage observability hook failed", exc_info=True)
        return {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), *outcome.messages]}
