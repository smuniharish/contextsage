"""All-parameters verification example.

Every constructor parameter of ``IntelligentSummarizationMiddleware`` is set
to an explicit, non-default value here, and each one's effect is checked
against something observable: the resulting message list, the emitted
``SummarizationEvent``, or middleware-internal state (provenance store,
observability hook). This is the single example that exercises the full
constructor surface at once, rather than one parameter at a time.

Uses a real chat model (see examples/_llm.py); requires EXPLABS_API_KEY.
"""

from __future__ import annotations

import asyncio
import re

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from _llm import build_recording_model
from contextiq import IntelligentSummarizationMiddleware
from contextiq.budget.tokens import TiktokenTokenCounter, TokenCounter
from contextiq.classification.signals import (
    DEFAULT_ERROR_KEYWORDS_PATTERN,
    DEFAULT_IDENTIFIER_PATTERNS,
    DEFAULT_SEVERITY_PATTERN,
)
from contextiq.core.models import ContentSignals
from contextiq.observability.events import ObservabilityHook, SummarizationEvent
from contextiq.parsers.base import ContentParser

CUSTOM_SUMMARY_PROMPT_MARKER = "CONTEXTIQ-ALL-PARAMS-DEMO-PROMPT"
ESCALATION_ID = "ESC-4482"
WIDGET_CODE = "WGT#88214"

# Custom classification overrides, composed additively with the built-in
# defaults (the documented pattern for `severity_pattern`/
# `error_keywords_pattern`) so existing error/severity detection keeps
# working while also recognizing an application-specific vocabulary that
# none of the built-ins would ever match.
CUSTOM_IDENTIFIER_PATTERNS = (*DEFAULT_IDENTIFIER_PATTERNS, re.compile(r"\bWGT#\d+\b"))
CUSTOM_ERROR_KEYWORDS_PATTERN = re.compile(
    rf"{DEFAULT_ERROR_KEYWORDS_PATTERN.pattern}|\bkaboomed\b", re.IGNORECASE
)
CUSTOM_SEVERITY_PATTERN = re.compile(rf"{DEFAULT_SEVERITY_PATTERN.pattern}|\bSNAFU\b")


# -- 1. custom `parsers` -------------------------------------------------------------


class EscalationTicketParser(ContentParser):
    """Domain-specific detector: classifies escalation-ticket text as its own
    kind (``"escalation_ticket"``) instead of falling through to plain TEXT.
    Demonstrates the ``parsers`` constructor parameter accepting a plain
    list of custom :class:`ContentParser` instances (no registry ceremony).
    """

    kind = "escalation_ticket"

    def detect(self, text: str) -> ContentSignals | None:
        if "Escalation ticket" in text and ESCALATION_ID in text:
            return ContentSignals(kind=self.kind, confidence=0.99)
        return None


# -- 2. custom `token_counter` -------------------------------------------------------


class CountingTokenCounter(TokenCounter):
    """Wraps the real tiktoken counter and records how many times it is
    called, proving a custom ``token_counter`` is actually used internally
    rather than silently ignored.
    """

    def __init__(self) -> None:
        self._inner = TiktokenTokenCounter(encoding_name="cl100k_base")
        self.text_calls = 0
        self.message_calls = 0

    def count_text(self, text: str) -> int:
        self.text_calls += 1
        return self._inner.count_text(text)

    def count_messages(self, messages) -> int:
        self.message_calls += 1
        return self._inner.count_messages(messages)


# -- 3. custom `observability_hook` --------------------------------------------------


class RecordingObservabilityHook(ObservabilityHook):
    """Collects every emitted event instead of logging it, proving
    ``observability_hook`` overrides the default logger.
    """

    def __init__(self) -> None:
        self.events: list[SummarizationEvent] = []

    def __call__(self, event: SummarizationEvent) -> None:
        self.events.append(event)


def build_large_ticket_conversation() -> list:
    """A conversation large enough to make token-budget trimming observable.

    Every message carries an explicit ``id`` (provenance only records
    ``source_message_ids`` for messages that have one), and the escalation
    sentence pairs the ``ESC-4482`` identifier with an explicit error
    keyword ("failed") so the importance engine tags it
    ``identifier_in_error_context`` -- the one reason that forces
    MUST_PRESERVE regardless of the numeric importance threshold.

    Two Human messages appear before the kept tail (msg-1 and msg-5) so
    LangChain's own message trimmer (``start_on="human"``) has more than
    one place it is allowed to start the window it hands to the summary
    model -- which is what makes ``trim_tokens_to_summarize`` produce a
    genuinely different, non-empty request instead of an all-or-nothing
    "too long to summarize" fallback.
    """
    log_lines = "\n".join(
        f"2024-07-01T00:{minute:02d}:00 INFO worker heartbeat ok" for minute in range(300)
    )
    ticket_report = (
        f"Escalation ticket {ESCALATION_ID} opened: customer reports repeated "
        "failed payment attempts contacting the payments API after the last deploy."
    )
    return [
        HumanMessage(
            content="Can you check on our open escalations and recent worker logs?",
            id="msg-1",
        ),
        AIMessage(
            content="",
            id="msg-2",
            tool_calls=[
                {"id": "call-1", "name": "get_escalations", "args": {}},
                {"id": "call-2", "name": "get_worker_logs", "args": {}},
            ],
        ),
        # Small, identifier-bearing unit: stays MUST_PRESERVE and untouched.
        ToolMessage(content=ticket_report, tool_call_id="call-1", id="msg-3"),
        # Large, repetitive, non-error unit: kept literal by ContextIQ (it is
        # the region LangGraph's own model call is expected to compress),
        # which is exactly why trim_tokens_to_summarize matters downstream.
        ToolMessage(content=log_lines, tool_call_id="call-2", id="msg-3b"),
        AIMessage(content="Looking into it now, checking regional impact.", id="msg-4"),
        HumanMessage(content="Also, is this affecting all regions?", id="msg-5"),
        AIMessage(content="Not yet confirmed, will report back.", id="msg-6"),
        # Deliberately not flagged by any built-in error/identifier pattern:
        # proves `identifier_patterns`/`error_keywords_pattern`/
        # `severity_pattern` are what make this fact protected, not a
        # built-in default.
        HumanMessage(
            content=(
                f"Also flagging {WIDGET_CODE}: the checkout widget completely "
                "kaboomed, SNAFU status confirmed."
            ),
            id="msg-6b",
        ),
        HumanMessage(content="Any update on timing?", id="tail-1"),
        AIMessage(content="Investigating; will report back shortly.", id="tail-2"),
        HumanMessage(content="Please prioritize this one.", id="tail-3"),
    ]


def main() -> None:
    recording_model = build_recording_model()
    token_counter = CountingTokenCounter()
    observability_hook = RecordingObservabilityHook()
    parsers = [EscalationTicketParser()]

    max_context_tokens = 5_000
    reserved_output_tokens = 500
    safety_margin = 0.05
    summarization_overhead_tokens = 200
    keep_count = 3

    middleware = IntelligentSummarizationMiddleware(
        model=recording_model,
        trigger=("tokens", 40),
        keep=("messages", keep_count),
        policy="maximum_preservation",
        maximum_context_tokens=max_context_tokens,
        reserved_output_tokens=reserved_output_tokens,
        safety_margin=safety_margin,
        summarization_overhead_tokens=summarization_overhead_tokens,
        validation_enabled=True,
        observability_enabled=True,
        observability_hook=observability_hook,
        provenance_enabled=True,
        token_counter=token_counter,
        parsers=parsers,
        severity_pattern=CUSTOM_SEVERITY_PATTERN,
        error_keywords_pattern=CUSTOM_ERROR_KEYWORDS_PATTERN,
        identifier_patterns=CUSTOM_IDENTIFIER_PATTERNS,
        summary_prompt=f"{CUSTOM_SUMMARY_PROMPT_MARKER}: summarize concisely.",
        trim_tokens_to_summarize=60,
    )

    conversation = build_large_ticket_conversation()
    result = middleware.before_model({"messages": conversation}, None)
    assert result is not None, "expected summarization to trigger"
    final_messages = result["messages"]
    combined_text = "\n".join(str(getattr(m, "content", "")) for m in final_messages)

    print("=== 1. model ===")
    print("real network call succeeded:", len(recording_model.call_log) >= 1)

    print("=== 2. trigger ===")
    control = IntelligentSummarizationMiddleware(
        model=recording_model,
        trigger=("tokens", 10_000_000),  # unreachable -> should NOT trigger
        keep=("messages", keep_count),
    )
    control_result = control.before_model({"messages": conversation}, None)
    print("low trigger fired:", result is not None)
    print("unreachable trigger correctly did not fire:", control_result is None)

    print("=== 3. keep ===")
    original_tail_ids = {"tail-1", "tail-2", "tail-3"}
    preserved_tail_ids = {getattr(m, "id", None) for m in final_messages} & original_tail_ids
    print(f"keep={keep_count} preserved the last {keep_count} messages verbatim:")
    print("  ", preserved_tail_ids == original_tail_ids)

    print("=== 4. policy (maximum_preservation) ===")
    print(f"{ESCALATION_ID} preserved:", ESCALATION_ID in combined_text)

    print(
        "=== 5/6/7/8. maximum_context_tokens / reserved_output_tokens / "
        "safety_margin / summarization_overhead_tokens ==="
    )
    assert observability_hook.events, "expected an observability event"
    event = observability_hook.events[0]

    def available_tokens_for(max_tokens: int, reserved: int, margin: float, overhead: int) -> int:
        # Only inspects the internal, no-network-call budget analyzer to
        # isolate each parameter's marginal effect on available_tokens.
        probe = IntelligentSummarizationMiddleware(
            model=recording_model,
            maximum_context_tokens=max_tokens,
            reserved_output_tokens=reserved,
            safety_margin=margin,
            summarization_overhead_tokens=overhead,
        )
        return probe._budget_analyzer.analyze(conversation).available_input_tokens

    baseline = available_tokens_for(5_000, 500, 0.0, 0)
    more_reserved = available_tokens_for(5_000, 1_000, 0.0, 0)
    more_margin = available_tokens_for(5_000, 500, 0.10, 0)
    more_context = available_tokens_for(6_000, 500, 0.0, 0)
    more_overhead = available_tokens_for(5_000, 500, 0.0, 200)
    print(
        "reserved_output_tokens: +500 reserved -> available drops by 500:",
        baseline - more_reserved == 500,
    )
    print(
        "safety_margin: 10% of 5000 -> available drops by 500:",
        baseline - more_margin == round(5_000 * 0.10),
    )
    print(
        "maximum_context_tokens: +1000 window -> available rises by 1000:",
        more_context - baseline == 1_000,
    )
    print(
        "summarization_overhead_tokens: +200 overhead -> available drops by 200:",
        baseline - more_overhead == 200,
    )
    actual_budget = middleware._budget_analyzer.analyze(conversation)
    print(
        "event.available_tokens matches the middleware's own budget analyzer:",
        event.available_tokens == actual_budget.available_input_tokens,
    )

    print("=== 9. validation_enabled ===")
    print("validation ran (not skipped):", event.validation_status != "skipped")
    no_validation = IntelligentSummarizationMiddleware(
        model=recording_model, validation_enabled=False, trigger=("tokens", 40)
    )
    # No live call needed: only inspecting constructor-time wiring here.
    print(
        "validation_enabled=False wired correctly:",
        no_validation._validation_enabled is False,
    )

    print("=== 10. observability_enabled / observability_hook ===")
    print("custom hook received the event:", len(observability_hook.events) == 1)
    disabled_observability = IntelligentSummarizationMiddleware(
        model=recording_model, observability_enabled=False, trigger=("tokens", 40)
    )
    print(
        "observability_enabled=False installs a NullObservabilityHook:",
        type(disabled_observability._observability_hook).__name__ == "NullObservabilityHook",
    )

    print("=== 11. provenance_enabled ===")
    print("provenance manager attached:", middleware._provenance is not None)
    summary_id = middleware._lineage.all()[-1].summary_id
    links = asyncio.run(middleware._provenance.alineage(summary_id))
    print("provenance links recorded for the summary:", len(links) > 0)
    no_provenance = IntelligentSummarizationMiddleware(
        model=recording_model, provenance_enabled=False, trigger=("tokens", 40)
    )
    print(
        "provenance_enabled=False leaves provenance manager unset:",
        no_provenance._provenance is None,
    )

    print("=== 12. token_counter ===")
    print(
        "custom token counter was invoked:",
        token_counter.text_calls > 0 or token_counter.message_calls > 0,
    )

    print("=== 13. parsers ===")
    print(
        "custom escalation_ticket kind detected:",
        event.content_signal_counts.get("escalation_ticket", 0) > 0,
    )

    print("=== 14. severity_pattern / error_keywords_pattern / identifier_patterns ===")
    print(f"{WIDGET_CODE} preserved (protected only by the custom patterns):")
    print("  ", WIDGET_CODE in combined_text)
    # Confirm the effect is genuinely from the override, not a coincidence:
    # the *default* detector would neither extract WIDGET_CODE as an
    # identifier nor flag "kaboomed"/"SNAFU" as error/severity signals.
    default_detector = IntelligentSummarizationMiddleware(
        model=recording_model
    )._decomposer._detector
    default_signals = default_detector.detect(
        f"Also flagging {WIDGET_CODE}: the checkout widget completely "
        "kaboomed, SNAFU status confirmed."
    )
    print(
        "default detector does NOT extract it (proves the override, not a default, did):",
        WIDGET_CODE not in default_signals.identifiers
        and default_signals.has_error is False
        and default_signals.severity is None,
    )

    print("=== 15. summary_prompt ===")
    sent_texts = [str(getattr(m, "content", "")) for call in recording_model.call_log for m in call]
    print("custom summary_prompt reached the real model call:")
    print("  ", any(CUSTOM_SUMMARY_PROMPT_MARKER in text for text in sent_texts))

    print("=== 16. trim_tokens_to_summarize ===")
    loose_trim_model = build_recording_model()
    loose_middleware = IntelligentSummarizationMiddleware(
        model=loose_trim_model,
        trigger=("tokens", 40),
        keep=("messages", keep_count),
        policy="maximum_preservation",
        trim_tokens_to_summarize=4_000,  # much larger than the main run's 60
    )
    loose_result = loose_middleware.before_model({"messages": conversation}, None)
    assert loose_result is not None, "expected the loose-trim run to trigger too"

    def tokens_sent(model: object) -> int:
        return sum(
            token_counter._inner.count_text(str(getattr(m, "content", "")))
            for call in model.call_log  # type: ignore[attr-defined]
            for m in call
        )

    tight_tokens = tokens_sent(recording_model)
    loose_tokens = tokens_sent(loose_trim_model)
    print("tokens sent with trim_tokens_to_summarize=60:  ", tight_tokens)
    print("tokens sent with trim_tokens_to_summarize=4000:", loose_tokens)
    print("trim_tokens_to_summarize bounds what is sent to the model:", tight_tokens < loose_tokens)


if __name__ == "__main__":
    main()
