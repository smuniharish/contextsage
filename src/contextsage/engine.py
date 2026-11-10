"""`ContextSummarizer`: framework-agnostic, information-aware summarization."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Self

from agxai import XAIRuntime
from opentelemetry import trace
from parsefabric import ChatMessage, LanguageModel
from parsefabric.execution import ThreadExecutionBackend

from contextsage._pipeline.budget import (
    DEFAULT_MAXIMUM_CONTEXT_TOKENS,
    Budget,
    Trigger,
    resolve_keep,
    validate_maximum_context_tokens,
)
from contextsage._pipeline.decomposition import Decomposer
from contextsage._pipeline.lineage import new_summary_id, replaced_summaries, stamp, summary_message
from contextsage._pipeline.models import EMPTY_ANALYSIS, Prepared
from contextsage._pipeline.pipeline import Pipeline
from contextsage._pipeline.provenance import ProvenanceRecorder
from contextsage._pipeline.recovery import fallback, restate
from contextsage._pipeline.signals import DEFAULT_IDENTIFIER_PATTERNS
from contextsage._pipeline.summary import DEFAULT_SUMMARY_PROMPT, fit, summary_text, transcript
from contextsage._pipeline.validation import validate
from contextsage._pipeline.window import cutoff
from contextsage.contracts import EventSink, PreservationPolicy, TokenCounter
from contextsage.errors import ConfigurationError, ContextSageError
from contextsage.events import SummarizationEvent
from contextsage.messages import Message
from contextsage.parsing import ParsingOptions
from contextsage.policies import BalancedPolicy
from contextsage.provenance import create_agxai_runtime
from contextsage.sinks import LoggingEventSink, deliver
from contextsage.tokens import TokenizerTokenCounter

if TYPE_CHECKING:
    from collections.abc import Sequence
    from types import TracebackType

    from agxai import ProvenanceLink
    from parsefabric.execution import ExecutionBackend

    from contextsage._pipeline.budget import Decision
    from contextsage.events import RecoveryStatus, ValidationStatus

__all__ = ["ContextSummarizer", "SummarizationResult"]

logger = logging.getLogger("contextsage")
_tracer = trace.get_tracer("contextsage")

type ContextSize = tuple[str, int | float]
type TriggerSpec = ContextSize | dict[str, int | float] | list[ContextSize | dict[str, int | float]]


@dataclass(frozen=True, slots=True)
class SummarizationResult:
    """The rewritten history and the event describing the rewrite.

    Attributes:
        messages: The history to use from now on. It replaces the whole input
            history, including any leading system messages, which are kept.
        event: Counts, ratios and statuses of the rewrite.
    """

    messages: tuple[Message, ...]
    event: SummarizationEvent


@dataclass(frozen=True, slots=True)
class _Outcome:
    messages: list[Message]
    summary_id: str | None
    generation: int
    source_ids: tuple[str, ...]
    validation_status: ValidationStatus
    recovery_status: RecoveryStatus


def _positive_or_none(value: object, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigurationError(f"{name} must be a positive integer or None")
    return value


def _instance[T](value: object, expected: type[T], name: str) -> T:
    if not isinstance(value, expected):
        raise ConfigurationError(
            f"{name} must be a {expected.__module__.split('.')[0]}.{expected.__name__}"
        )
    return value


class ContextSummarizer:
    """Information-aware summarization of an agent's message history.

    `summarize` decides whether the history needs summarizing. When it does,
    ContextSage parses every message with parsefabric into content units
    (prose, JSON, logs, tables, code, stack traces), scores them, decides what
    must be preserved, and losslessly compacts low-value structured content.
    The summary model then summarizes the older messages, ContextSage verifies
    that every must-preserve fact survived and restates any that did not, and
    links the summarized messages to the summary in an agxai provenance store.

    The engine works with `contextsage.Message` objects, so it fits any agent
    framework: convert native messages with a `contextsage.FrameworkAdapter`,
    or use a ready-made integration such as
    ``contextsage.integrations.langchain``.

    Example:
        ```python
        from contextsage import ContextSummarizer, Message

        async with ContextSummarizer(model, trigger=("tokens", 100_000)) as summarizer:
            result = await summarizer.summarize(history, thread_id="thread-1")
            if result is not None:
                history = list(result.messages)
        ```

    Args:
        model: The parsefabric ``LanguageModel`` that writes summaries.
        trigger: When to summarize: ``("tokens", n)``, ``("messages", n)``,
            ``("fraction", f)``, a clause such as
            ``{"tokens": 4000, "messages": 10}`` whose conditions must all
            hold, or a list in which any item may hold. ``None`` (the default)
            summarizes when the history no longer fits the token budget
            described by the next four arguments.
        keep: How much recent history stays verbatim, as ``("messages", n)``,
            ``("tokens", n)`` or ``("fraction", f)``, a share of
            ``maximum_context_tokens``.
        policy: How readily content is compacted. Defaults to
            `contextsage.BalancedPolicy`.
        maximum_context_tokens: The model's context window.
        reserved_output_tokens: Tokens kept free for the model's response.
        safety_margin: Fraction of the context window held back as a buffer.
        summarization_overhead_tokens: Tokens kept free for the system prompt,
            tool schemas and the summary call's own prompt.
        token_counter: Counts the tokens of messages. Defaults to
            `contextsage.TokenizerTokenCounter`.
        identifier_patterns: Regular expressions for identifiers that must
            survive summarization. Replaces
            `contextsage.DEFAULT_IDENTIFIER_PATTERNS`; pass
            ``[*DEFAULT_IDENTIFIER_PATTERNS, re.compile(...)]`` to extend them.
        validation_enabled: Verify the rewritten history and restate missing
            facts.
        summary_prompt: Prompt for the summary model, with a ``{messages}``
            placeholder for the transcript being summarized.
        trim_tokens_to_summarize: Token budget for the transcript sent to the
            summary model, or ``None`` to send it all.
        parsing: How message text is parsed; see `contextsage.ParsingOptions`.
        sink: Receives a `contextsage.SummarizationEvent` for each rewrite.
            Defaults to `contextsage.LoggingEventSink`.
        runtime: The agxai runtime whose ``ProvenanceStore`` and identity
            record summary lineage. Build one with
            `contextsage.create_agxai_runtime`. Defaults to a runtime with an
            in-memory store, which keeps links until the process exits.
        propagate_errors: Exception types from the summary model that are
            re-raised instead of triggering the trimming fallback, such as a
            framework's control-flow exceptions.

    Raises:
        ConfigurationError: If an argument is invalid.
    """

    def __init__(
        self,
        model: LanguageModel,
        *,
        trigger: TriggerSpec | None = None,
        keep: ContextSize = ("messages", 20),
        policy: PreservationPolicy | None = None,
        maximum_context_tokens: int = DEFAULT_MAXIMUM_CONTEXT_TOKENS,
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
        propagate_errors: Sequence[type[BaseException]] = (),
    ) -> None:
        self._model = _instance(model, LanguageModel, "model")
        self._policy = (
            BalancedPolicy() if policy is None else _instance(policy, PreservationPolicy, "policy")
        )
        self._counter = (
            TokenizerTokenCounter()
            if token_counter is None
            else _instance(token_counter, TokenCounter, "token_counter")
        )
        self._parsing = (
            ParsingOptions() if parsing is None else _instance(parsing, ParsingOptions, "parsing")
        )
        self._owns_sink = sink is None
        self._sink = LoggingEventSink() if sink is None else _instance(sink, EventSink, "sink")
        self._owns_runtime = runtime is None
        self._runtime = (
            create_agxai_runtime() if runtime is None else _instance(runtime, XAIRuntime, "runtime")
        )
        if not isinstance(summary_prompt, str) or "{messages}" not in summary_prompt:
            raise ConfigurationError("summary_prompt must contain a {messages} placeholder")
        self._prompt = summary_prompt
        self._trim = _positive_or_none(trim_tokens_to_summarize, "trim_tokens_to_summarize")
        patterns = (
            DEFAULT_IDENTIFIER_PATTERNS
            if identifier_patterns is None
            else tuple(identifier_patterns)
        )
        if not all(
            isinstance(pattern, re.Pattern) and isinstance(pattern.pattern, str)
            for pattern in patterns
        ):
            raise ConfigurationError("identifier_patterns must be compiled text regexes")
        self._patterns = patterns
        if isinstance(propagate_errors, type) or not all(
            isinstance(error, type) and issubclass(error, BaseException)
            for error in propagate_errors
        ):
            raise ConfigurationError("propagate_errors must be a sequence of exception types")
        self._propagate = tuple(propagate_errors)
        if not isinstance(validation_enabled, bool):
            raise ConfigurationError("validation_enabled must be a bool")
        self._validation_enabled = validation_enabled
        self._budget = Budget(
            maximum_context_tokens=validate_maximum_context_tokens(maximum_context_tokens),
            reserved_output_tokens=reserved_output_tokens,
            safety_margin=safety_margin,
            summarization_overhead_tokens=summarization_overhead_tokens,
        )
        self._keep = resolve_keep(keep, self._budget.maximum_context_tokens)
        self._trigger = Trigger(trigger, self._budget)
        self._provenance = ProvenanceRecorder(self._runtime)
        self._pipeline: Pipeline | None = None
        self._backend: ExecutionBackend | None = self._parsing.backend
        self._owns_backend = self._backend is None
        self._lock = asyncio.Lock()
        self._closed = False

    @property
    def runtime(self) -> XAIRuntime:
        """The agxai runtime that records summary lineage."""
        return self._runtime

    @property
    def sink(self) -> EventSink:
        """The sink that receives summarization events."""
        return self._sink

    @property
    def policy(self) -> PreservationPolicy:
        """The preservation policy in effect."""
        return self._policy

    async def prepare(self) -> None:
        """Load parsing resources, such as tree-sitter grammars, now.

        `summarize` loads them on first use and, if the grammars cannot be
        loaded, continues without code detection. Call `prepare` at start-up
        to fail fast instead.

        Raises:
            ConfigurationError: If parsing resources cannot be loaded.
        """
        await self._ensure_pipeline(strict=True)

    async def summarize(
        self,
        messages: Sequence[Message],
        *,
        thread_id: str | None = None,
        graph_id: str | None = None,
    ) -> SummarizationResult | None:
        """Summarize ``messages`` if the trigger fires.

        Args:
            messages: The full message history, oldest first.
            thread_id: The conversation the history belongs to. Provenance is
                scoped by it, so pass the same value to `lineage`.
            graph_id: The agent graph, recorded with provenance links.
                Defaults to the runtime's ``graph_id``.

        Returns:
            The rewritten history, or ``None`` when it is left unchanged.

        Raises:
            TypeError: If an item of ``messages`` is not a `contextsage.Message`.
            ContextSageError: If the summarizer is closed.
        """
        if self._closed:
            raise ContextSageError("the summarizer is closed")
        history = list(messages)
        if not all(isinstance(message, Message) for message in history):
            raise TypeError("messages must be contextsage.Message objects")
        started = time.perf_counter()
        with _tracer.start_as_current_span("contextsage.summarize") as span:
            tokens = await self._counter.count(history)
            decision = self._trigger.evaluate(tokens=tokens, messages=len(history))
            span.set_attribute("contextsage.triggered", decision is not None)
            if decision is None:
                return None
            prepared = await self._analyze(history)
            try:
                outcome = await self._summarize(prepared)
            except self._propagate:
                raise
            except Exception as error:
                outcome = await self._recover(prepared, error)
            if outcome is None:
                return None
            event = await self._event(
                history, tokens, decision, prepared, outcome, thread_id, started
            )
            span.set_attribute("contextsage.validation_status", event.validation_status)
            span.set_attribute("contextsage.recovery_status", event.recovery_status)
            if outcome.summary_id is not None and outcome.source_ids:
                with _tracer.start_as_current_span("contextsage.provenance"):
                    await self._provenance.record(
                        source_ids=outcome.source_ids,
                        summary_id=outcome.summary_id,
                        thread_id=thread_id,
                        graph_id=graph_id,
                        metadata=event.as_dict(),
                    )
            await deliver(self._sink, event)
            return SummarizationResult(tuple(outcome.messages), event)

    async def lineage(
        self, summary_id: str, *, thread_id: str | None = None
    ) -> tuple[ProvenanceLink, ...]:
        """Return the provenance of a summary, nearest links first.

        Walks back from the summary through every earlier summary it replaced
        to the original messages.

        Args:
            summary_id: ID of a summary message, also reported as
                `contextsage.SummarizationEvent.summary_id`.
            thread_id: The thread passed to `summarize`.

        Returns:
            The ``derived_from`` links, each from a source to what it became.
        """
        return await self._provenance.lineage(summary_id, thread_id)

    async def delete_lineage(self, *, thread_id: str | None = None) -> int:
        """Delete the provenance recorded for a conversation thread.

        Use it when a conversation is erased, for example to honor a
        retention policy or a deletion request. Only links ContextSage
        recorded for the thread are removed; agxai run records of the agent
        itself are kept.

        Args:
            thread_id: The thread passed to `summarize`.

        Returns:
            The number of records the ``ProvenanceStore`` removed.
        """
        return await self._provenance.delete(thread_id)

    async def aclose(self) -> None:
        """Flush the sink and release what the summarizer created.

        The default sink, worker thread and agxai runtime are closed; a sink,
        backend or runtime you passed in is flushed at most, never closed.
        Idempotent.
        """
        if self._closed:
            return
        self._closed = True
        steps = [self._sink.close() if self._owns_sink else self._sink.flush()]
        if self._owns_backend and self._backend is not None:
            steps.append(self._backend.shutdown())
        if self._owns_runtime:
            steps.append(self._runtime.close())
        errors = [
            result
            for result in await asyncio.gather(*steps, return_exceptions=True)
            if isinstance(result, Exception)
        ]
        if errors:
            raise ExceptionGroup("contextsage could not close cleanly", errors)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    # -- steps ---------------------------------------------------------------

    async def _ensure_pipeline(self, *, strict: bool) -> tuple[Pipeline, ExecutionBackend]:
        async with self._lock:
            if self._backend is None:
                # One worker keeps every parse on the same worker event loop.
                self._backend = ThreadExecutionBackend(max_workers=1)
            if self._pipeline is None:
                options = self._parsing
                try:
                    await options.prepare()
                except ConfigurationError:
                    if strict:
                        raise
                    logger.warning(
                        "contextsage could not load code-detection grammars; "
                        "continuing without code detection",
                        exc_info=True,
                    )
                    options = replace(options, code_detector=None)
                decomposer = Decomposer(
                    await options.build_parser(),
                    options.build_engine(),
                    self._patterns,
                    max_concurrency=options.max_concurrency,
                )
                self._pipeline = Pipeline(decomposer, self._policy)
            return self._pipeline, self._backend

    async def _analyze(self, history: list[Message]) -> Prepared:
        pipeline, backend = await self._ensure_pipeline(strict=False)
        with _tracer.start_as_current_span("contextsage.analyze"):
            try:
                return await backend.run(pipeline.prepare, history)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.error(
                    "contextsage could not analyze the history; summarizing it unanalyzed",
                    exc_info=error,
                )
                return Prepared(messages=history, analysis=EMPTY_ANALYSIS, compacted_units=0)

    async def _summarize(self, prepared: Prepared) -> _Outcome | None:
        messages = prepared.messages
        leading = 0
        while leading < len(messages) and messages[leading].role == "system":
            leading += 1
        system, conversation = messages[:leading], messages[leading:]
        cut = await cutoff(conversation, self._keep, self._counter)
        if cut == 0:
            return self._finalize(prepared, None, 0)
        text = await fit(transcript(conversation[:cut]), self._trim, self._counter)
        with _tracer.start_as_current_span("contextsage.summary_model"):
            reply = await self._model.complete(
                [ChatMessage("user", self._prompt.replace("{messages}", text))]
            )
        if not isinstance(reply, str) or not reply.strip():
            raise ContextSageError("the summary model returned an empty summary")
        summary = summary_message(summary_text(reply))
        return self._finalize(prepared, [*system, summary, *conversation[cut:]], leading)

    def _finalize(
        self, prepared: Prepared, summarized: list[Message] | None, index: int
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
        summarized[index] = stamp(
            summarized[index],
            summary_id=summary_id,
            generation=generation,
            source_summary_ids=replaced,
            facts=facts,
        )
        source_ids = tuple(
            message.id for message in prepared.messages if message.id and message.id not in kept_ids
        )
        validation_status: ValidationStatus = "disabled"
        recovery_status: RecoveryStatus = "none_needed"
        messages = summarized
        if self._validation_enabled:
            with _tracer.start_as_current_span("contextsage.validate"):
                result = validate(messages, facts)
            validation_status = "passed"
            if result.missing:
                messages = restate(messages, result.missing)
                validation_status = "failed_recovered"
                recovery_status = "restated_facts"
            if result.orphaned_tool_results:
                logger.warning(
                    "contextsage found tool results without their tool call "
                    "after summarization: %s",
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

    async def _recover(self, prepared: Prepared, error: Exception) -> _Outcome:
        logger.warning(
            "contextsage summary model failed (%s); trimming to the keep window",
            type(error).__name__,
            exc_info=error,
        )
        facts = prepared.analysis.facts
        messages, summary_index = await fallback(
            prepared.messages,
            keep=self._keep,
            counter=self._counter,
            facts=lambda window: validate(window, facts).missing,
        )
        kept = {id(message) for message in messages}
        source_ids = tuple(
            message.id for message in prepared.messages if message.id and id(message) not in kept
        )
        summary_id: str | None = None
        generation = 0
        if summary_index is not None:
            kept_ids = {message.id for message in messages if message.id}
            generation, replaced = replaced_summaries(prepared.messages, kept_ids)
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

    async def _event(
        self,
        history: list[Message],
        tokens: int,
        decision: Decision,
        prepared: Prepared,
        outcome: _Outcome,
        thread_id: str | None,
        started: float,
    ) -> SummarizationEvent:
        output_tokens = await self._counter.count(outcome.messages)
        analysis = prepared.analysis
        return SummarizationEvent(
            summary_id=outcome.summary_id,
            generation=outcome.generation,
            thread_id=thread_id,
            trigger_reason=decision.reason,
            input_messages=len(history),
            input_tokens=tokens,
            available_tokens=self._budget.available_tokens,
            overflow_tokens=decision.overflow_tokens,
            prepared_tokens=await self._counter.count(prepared.messages)
            if prepared.compacted_units
            else tokens,
            output_messages=len(outcome.messages),
            output_tokens=output_tokens,
            compression_ratio=output_tokens / tokens if tokens else 0.0,
            compacted_units=prepared.compacted_units,
            must_preserve_units=analysis.must_preserve_count,
            must_preserve_facts=len(analysis.facts),
            content_kinds=analysis.kind_counts(),
            validation_status=outcome.validation_status,
            recovery_status=outcome.recovery_status,
            policy=self._policy.name,
            latency_ms=(time.perf_counter() - started) * 1000,
        )
