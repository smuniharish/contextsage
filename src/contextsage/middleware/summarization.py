"""Public middleware: :class:`IntelligentSummarizationMiddleware`.

This is the single public entry point of ContextSage.
Internally it orchestrates every engine described in
``docs/architecture.md`` — it does not implement their logic itself
("no god object"):

    Observer -> Budget -> Decomposer -> Importance -> Relationships ->
    Preservation -> Planner -> Transformer -> LangGraph adapter ->
    Validator -> Recovery -> Reconstruction -> Lineage/Observability/Provenance
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, Any

from langchain.agents.middleware.summarization import ContextSize
from langchain.agents.middleware.types import AgentMiddleware, AgentState
from langchain.chat_models import init_chat_model
from langchain_core.messages import RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES

from contextsage.budget.analyzer import BudgetAnalyzer, BudgetConfig, infer_max_context_tokens
from contextsage.budget.tokens import TokenCounter, create_default_token_counter
from contextsage.classification.signals import StructuralSignalDetector
from contextsage.context.decomposition import ContextDecomposer
from contextsage.context.observer import ContextObserver
from contextsage.core.models import RecoveryOutcome, RelationType
from contextsage.core.reconstruction import apply_transformed_units, content_signal_counts
from contextsage.importance.engine import ImportanceEngine
from contextsage.integrations.langgraph.adapter import LangGraphSummarizationAdapter
from contextsage.integrations.langgraph_xai.provenance import ProvenanceManager
from contextsage.lineage.manager import LineageManager, find_prior_summary_ids
from contextsage.observability.events import (
    LoggingObservabilityHook,
    NullObservabilityHook,
    ObservabilityHook,
    SummarizationEvent,
)
from contextsage.parsers.base import ContentParser, ParserRegistry, default_registry
from contextsage.planning.planner import SummarizationPlanner
from contextsage.planning.trigger import TriggerSpec, evaluate_trigger
from contextsage.preservation.engine import Policy as PreservationPolicy
from contextsage.preservation.engine import PreservationEngine
from contextsage.recovery.manager import RecoveryManager
from contextsage.relationships.engine import RelationshipEngine, pair_tool_calls
from contextsage.transformation.engine import ContextTransformationEngine
from contextsage.validation.validator import SummaryValidator

if TYPE_CHECKING:
    from collections.abc import Sequence

    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import BaseMessage
    from langgraph.runtime import Runtime

Policy = PreservationPolicy

_DEFAULT_KEEP_MESSAGES = 20


class IntelligentSummarizationMiddleware(AgentMiddleware):
    """Intelligent, production-grade replacement for LangGraph's summarization middleware.

    Example:
        ```python
        from langchain.agents import create_agent
        from contextsage import IntelligentSummarizationMiddleware

        middleware = IntelligentSummarizationMiddleware(
            model=model,
            trigger=("tokens", 100_000),
            keep=("messages", 20),
        )

        agent = create_agent(model=model, tools=tools, middleware=[middleware])
        ```

    Args:
        model: The chat model (or ``init_chat_model``-style model string)
            used both for LangGraph's underlying semantic summarization call
            and, unless overridden, for token counting/context-window
            inference.
        trigger: When summarization should fire, e.g. ``("tokens", 100_000)``
            or ``("fraction", 0.8)``. See :mod:`contextsage.planning.trigger`.
        keep: How much recent context to always keep verbatim, e.g.
            ``("messages", 20)``.
        policy: Preservation aggressiveness — ``"maximum_preservation"``,
            ``"balanced"`` (default), or ``"maximum_compression"``. See
            :mod:`contextsage.preservation.engine`.
        maximum_context_tokens: Override the model's inferred context window.
        reserved_output_tokens: Tokens reserved for the model's own response,
            subtracted from the available budget.
        safety_margin: Fraction of the context window held back as a buffer.
        summarization_overhead_tokens: Tokens reserved for the summarization
            call's own prompt/response overhead, subtracted from the
            available budget alongside ``reserved_output_tokens`` and the
            safety margin.
        validation_enabled: Whether post-summarization validation (must-
            preserve facts, contradiction survival) runs before accepting a
            summary.
        observability_enabled: Whether the default logging observability
            hook is installed when ``observability_hook`` is not given.
        observability_hook: Custom :class:`~contextsage.observability.events.ObservabilityHook`
            to receive :class:`~contextsage.observability.events.SummarizationEvent`
            callbacks (metrics/tracing integration point).
        provenance_enabled: Whether ``langgraph-xai`` provenance/lineage
            tracking is enabled for summarized units.
        token_counter: Custom :class:`~contextsage.budget.tokens.TokenCounter`
            (defaults to a ``cl100k_base`` ``TiktokenTokenCounter``).
        parsers: Custom :class:`~contextsage.parsers.base.ContentParser`
            instances to detect domain-specific content kinds (e.g. a
            protobuf or SQL parser). Given parsers are tried, in order,
            *before* the built-in JSON/table/code/log/error parsers, so a
            custom parser can override detection for its kind while every
            other kind still falls back to the built-ins. Omit to use only
            the built-in parsers.
        severity_pattern: Custom regex overriding how log/error severity
            (``DEBUG``/``INFO``/``ERROR``/...) is recognized. This is a
            classification-layer concern, distinct from ``parsers`` — it
            applies uniformly to every detected content kind, not just
            log/error regions. Defaults to
            :data:`~contextsage.classification.signals.DEFAULT_SEVERITY_PATTERN`.
        error_keywords_pattern: Custom regex overriding which keywords mark
            a region as an error for preservation purposes (e.g. an
            application's own incident vocabulary). Defaults to
            :data:`~contextsage.classification.signals.DEFAULT_ERROR_KEYWORDS_PATTERN`.
        identifier_patterns: Custom regexes overriding which substrings are
            extracted as must-preserve identifiers (e.g. an application's
            own ticket/order-ID format). Defaults to
            :data:`~contextsage.classification.signals.DEFAULT_IDENTIFIER_PATTERNS`.
        summary_prompt: Custom prompt passed through to LangGraph's
            summarization call.
        trim_tokens_to_summarize: Token budget LangGraph is allowed to use
            while producing the summary itself.
    """

    def __init__(
        self,
        model: str | BaseChatModel,
        *,
        trigger: TriggerSpec = None,
        keep: ContextSize = (
            "messages",
            _DEFAULT_KEEP_MESSAGES,
        ),
        policy: Policy = "balanced",
        maximum_context_tokens: int | None = None,
        reserved_output_tokens: int = 4_000,
        safety_margin: float = 0.10,
        summarization_overhead_tokens: int = 2_000,
        validation_enabled: bool = True,
        observability_enabled: bool = True,
        observability_hook: ObservabilityHook | None = None,
        provenance_enabled: bool = True,
        token_counter: TokenCounter | None = None,
        parsers: Sequence[ContentParser] | None = None,
        severity_pattern: re.Pattern[str] | None = None,
        error_keywords_pattern: re.Pattern[str] | None = None,
        identifier_patterns: Sequence[re.Pattern[str]] | None = None,
        summary_prompt: str | None = None,
        trim_tokens_to_summarize: int | None = 4_000,
    ) -> None:
        super().__init__()
        if isinstance(model, str):
            model = init_chat_model(model)

        self._model = model
        self._trigger = trigger
        self._keep = keep
        self._policy = policy

        self._token_counter = token_counter or create_default_token_counter(model)
        max_context_tokens = maximum_context_tokens or infer_max_context_tokens(model)
        budget_config = BudgetConfig(
            maximum_context_tokens=max_context_tokens,
            reserved_output_tokens=reserved_output_tokens,
            safety_margin_fraction=safety_margin,
            summarization_overhead_tokens=summarization_overhead_tokens,
        )

        registry = ParserRegistry((*parsers, *default_registry())) if parsers else None
        detector_overrides: dict[str, Any] = {}
        if severity_pattern is not None:
            detector_overrides["severity_pattern"] = severity_pattern
        if error_keywords_pattern is not None:
            detector_overrides["error_keywords_pattern"] = error_keywords_pattern
        if identifier_patterns is not None:
            detector_overrides["identifier_patterns"] = identifier_patterns
        detector = StructuralSignalDetector(registry=registry, **detector_overrides)
        self._observer = ContextObserver(self._token_counter)
        self._budget_analyzer = BudgetAnalyzer(self._token_counter, budget_config)
        self._decomposer = ContextDecomposer(self._token_counter, detector=detector)
        self._importance_engine = ImportanceEngine()
        self._relationship_engine = RelationshipEngine()
        self._preservation_engine = PreservationEngine(policy=policy)
        self._planner = SummarizationPlanner()
        self._transformer = ContextTransformationEngine(self._token_counter)
        self._validator = SummaryValidator()
        self._recovery = RecoveryManager()
        self._lineage = LineageManager()

        self._validation_enabled = validation_enabled
        if observability_hook is not None:
            self._observability_hook: ObservabilityHook = observability_hook
        elif observability_enabled:
            self._observability_hook = LoggingObservabilityHook()
        else:
            self._observability_hook = NullObservabilityHook()

        self._provenance = ProvenanceManager() if provenance_enabled else None

        self._adapter = LangGraphSummarizationAdapter(
            model,
            keep=keep,
            summary_prompt=summary_prompt,
            trim_tokens_to_summarize=trim_tokens_to_summarize,
        )

    # -- LangGraph middleware hooks -------------------------------------------------

    def before_model(self, state: AgentState[Any], runtime: Runtime[Any]) -> dict[str, Any] | None:
        del runtime
        messages = list(state["messages"])
        started = time.monotonic()
        prepared = self._prepare(messages)
        if prepared is None:
            return None

        try:
            update = self._adapter.summarize(prepared.messages)
        except Exception as exc:
            return self._handle_summarization_failure(messages, prepared, exc, started)

        if update is None:
            return None
        return self._finalize(messages, prepared, update, started)

    async def abefore_model(
        self, state: AgentState[Any], runtime: Runtime[Any]
    ) -> dict[str, Any] | None:
        del runtime
        messages = list(state["messages"])
        started = time.monotonic()
        prepared = self._prepare(messages)
        if prepared is None:
            return None

        try:
            update = await self._adapter.asummarize(prepared.messages)
        except Exception as exc:
            return self._handle_summarization_failure(messages, prepared, exc, started)

        if update is None:
            return None
        result = self._finalize(messages, prepared, update, started)
        if self._provenance is not None and result is not None:
            source_ids = tuple(
                str(mid) for m in messages if (mid := getattr(m, "id", None)) is not None
            )
            summary_id = self._lineage.all()[-1].summary_id if self._lineage.all() else None
            if summary_id:
                await self._provenance.arecord_summary_provenance(
                    source_message_ids=source_ids, summary_id=summary_id
                )
        return result

    # -- internal pipeline -----------------------------------------------------------

    def _prepare(self, messages: Sequence[BaseMessage]) -> _PreparedContext | None:
        observed = self._observer.observe(messages)
        budget = self._budget_analyzer.analyze(messages)
        decision = evaluate_trigger(
            self._trigger, budget=budget, message_count=observed.total_messages
        )
        if not decision.required:
            return None

        units = self._decomposer.decompose(messages)
        units = self._importance_engine.score(units)
        relationships = self._relationship_engine.analyze(units)
        units = self._preservation_engine.classify(units, relationships)
        must_preserve_facts = self._preservation_engine.extract_must_preserve_facts(units)

        tool_pairs = pair_tool_calls(messages)
        protected_message_ids = tuple({mid for pair in tool_pairs.values() for mid in pair if mid})

        plan = self._planner.plan(
            units,
            required=True,
            trigger_reason=decision.reason,
            overflow_tokens=decision.overflow_tokens,
            must_preserve_facts=must_preserve_facts,
            protected_message_ids=protected_message_ids,
        )
        outcome = self._transformer.transform(units, plan)
        prepared_messages = apply_transformed_units(messages, outcome.units)
        contradictions = tuple(r for r in relationships if r.relation is RelationType.CONTRADICTS)

        return _PreparedContext(
            messages=prepared_messages,
            units=list(outcome.units),
            plan=plan,
            must_preserve_facts=must_preserve_facts,
            contradiction_relationships=contradictions,
            observed_total_tokens=observed.total_tokens,
            available_tokens=budget.available_input_tokens,
        )

    def _keep_count(self) -> int:
        kind, value = self._keep
        return int(value) if kind == "messages" else _DEFAULT_KEEP_MESSAGES

    def _handle_summarization_failure(
        self,
        original_messages: Sequence[BaseMessage],
        prepared: _PreparedContext,
        error: Exception,
        started: float,
    ) -> dict[str, Any]:
        recovered_messages, recovery_outcome = self._recovery.recover_from_summarization_failure(
            original_messages=original_messages,
            keep_count=self._keep_count(),
            must_preserve_facts=prepared.must_preserve_facts,
            error=error,
        )
        self._emit_event(
            prepared,
            summary_tokens=self._token_counter.count_messages(recovered_messages),
            validation_status="skipped",
            recovery_status=recovery_outcome.strategy,
            fallback_used=recovery_outcome.fallback_used,
            started=started,
        )
        return {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), *recovered_messages]}

    def _finalize(
        self,
        original_messages: Sequence[BaseMessage],
        prepared: _PreparedContext,
        update: dict[str, Any],
        started: float,
    ) -> dict[str, Any]:
        new_messages = update.get("messages", [])
        content_messages = [m for m in new_messages if not isinstance(m, RemoveMessage)]

        validation_status = "skipped"
        recovery_outcome = RecoveryOutcome(recovered=True, strategy="none_needed")
        if self._validation_enabled:
            validation_result = self._validator.validate(
                new_messages=content_messages,
                must_preserve_facts=prepared.must_preserve_facts,
                contradiction_relationships=prepared.contradiction_relationships,
            )
            if validation_result.passed:
                validation_status = "passed"
            else:
                validation_status = "failed_recovered"
                content_messages, recovery_outcome = self._recovery.recover_from_validation_failure(
                    messages=content_messages,
                    validation_result=validation_result,
                    must_preserve_facts=prepared.must_preserve_facts,
                )

        source_message_ids = tuple(
            mid for m in original_messages if (mid := getattr(m, "id", None))
        )
        source_summary_ids = find_prior_summary_ids(source_message_ids)
        summary_id = self._lineage.next_summary_id()
        summary_tokens = self._token_counter.count_messages(content_messages)
        prepared_tokens = sum(u.token_count for u in prepared.units)
        self._lineage.record(
            summary_id=summary_id,
            source_message_ids=source_message_ids,
            source_summary_ids=source_summary_ids,
            input_tokens=prepared.observed_total_tokens,
            prepared_tokens=prepared_tokens,
            summary_tokens=summary_tokens,
            selected_target_count=sum(len(t.unit_ids) for t in prepared.plan.targets),
            preservation_unit_count=len(prepared.plan.must_preserve_unit_ids),
            validation_status=validation_status,
            recovery_status=recovery_outcome.strategy,
            fallback_used=recovery_outcome.fallback_used,
        )

        if self._provenance is not None:
            self._provenance.record_summary_provenance(
                source_message_ids=source_message_ids, summary_id=summary_id
            )

        self._emit_event(
            prepared,
            summary_tokens=summary_tokens,
            validation_status=validation_status,
            recovery_status=recovery_outcome.strategy,
            fallback_used=recovery_outcome.fallback_used,
            started=started,
        )

        return {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), *content_messages]}

    def _emit_event(
        self,
        prepared: _PreparedContext,
        *,
        summary_tokens: int,
        validation_status: str,
        recovery_status: str,
        fallback_used: bool,
        started: float,
    ) -> None:
        prepared_tokens = sum(u.token_count for u in prepared.units)
        event = SummarizationEvent(
            trigger_reason=prepared.plan.trigger_reason,
            input_tokens=prepared.observed_total_tokens,
            available_tokens=prepared.available_tokens,
            overflow_tokens=prepared.plan.overflow_tokens,
            selected_target_count=sum(len(t.unit_ids) for t in prepared.plan.targets),
            content_signal_counts=content_signal_counts(prepared.units),
            prepared_tokens=prepared_tokens,
            summary_tokens=summary_tokens,
            compression_ratio=(
                summary_tokens / prepared.observed_total_tokens
                if prepared.observed_total_tokens
                else 0.0
            ),
            validation_status=validation_status,
            recovery_status=recovery_status,
            fallback_used=fallback_used,
            latency_ms=(time.monotonic() - started) * 1000,
        )
        self._observability_hook(event)


class _PreparedContext:
    """Internal carrier for the output of :meth:`_prepare` (not a public type)."""

    __slots__ = (
        "available_tokens",
        "contradiction_relationships",
        "messages",
        "must_preserve_facts",
        "observed_total_tokens",
        "plan",
        "units",
    )

    def __init__(
        self,
        *,
        messages: list[BaseMessage],
        units: list[Any],
        plan: Any,
        must_preserve_facts: tuple[str, ...],
        contradiction_relationships: tuple[Any, ...],
        observed_total_tokens: int,
        available_tokens: int,
    ) -> None:
        self.messages = messages
        self.units = units
        self.plan = plan
        self.must_preserve_facts = must_preserve_facts
        self.contradiction_relationships = contradiction_relationships
        self.observed_total_tokens = observed_total_tokens
        self.available_tokens = available_tokens
