"""The structured event emitted for every summarization."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

__all__ = ["RecoveryStatus", "SummarizationEvent", "ValidationStatus"]

type ValidationStatus = Literal[
    "passed", "failed_recovered", "failed_unrecovered", "skipped", "disabled"
]
"""Outcome of checking the rewritten history.

- ``passed``: every must-preserve fact survived and every tool result still
  follows its tool call. Compaction alone always passes, because it never
  removes must-preserve content.
- ``failed_recovered``: facts were missing and ContextSage restated them.
- ``failed_unrecovered``: a tool result lost its tool call, which restating
  facts cannot repair; ContextSage logs a warning.
- ``skipped``: there was no summary to check because the summary model failed.
- ``disabled``: validation is turned off (``validation_enabled=False``).
"""

type RecoveryStatus = Literal[
    "none_needed", "restated_facts", "trimmed_fallback", "none_applicable"
]
"""What ContextSage did after validation or a summary-model failure.

- ``none_needed``: nothing was missing, or validation is disabled.
- ``restated_facts``: missing facts were added verbatim to the summary message.
- ``trimmed_fallback``: the summary model failed, so the history was trimmed to
  the ``keep`` window, with a notice restating the latest user request and
  the facts the window lost.
- ``none_applicable``: a tool result lost its tool call, but no facts were
  missing, so there was nothing to restate.
"""


@dataclass(frozen=True, slots=True, kw_only=True)
class SummarizationEvent:
    """Aggregate, content-free record of one summarization.

    One event is logged to the ``contextsage`` logger at ``INFO`` level and
    passed to the optional ``observability_hook`` each time the middleware
    rewrites the message history. Events contain counts, ratios and statuses
    only: never message content, tool output or credentials.

    Attributes:
        summary_id: Message ID of the summary that now opens the history, or
            ``None`` when only deterministic compaction was applied.
        generation: How many summaries this one descends from: 1 for a first
            summary, 2 for a summary of a summary, and 0 when no summary was
            produced.
        thread_id: LangGraph thread the summary belongs to, if the agent runs
            with a checkpointer.
        trigger_reason: Why summarization ran.
        input_messages: Messages in the history before summarization.
        input_tokens: Tokens in the history before summarization.
        available_tokens: Input tokens available under the configured budget.
        overflow_tokens: Tokens over the trigger threshold or budget.
        prepared_tokens: Tokens after deterministic compaction, before the
            summary model ran.
        output_messages: Messages in the rewritten history.
        output_tokens: Tokens in the rewritten history.
        compression_ratio: ``output_tokens / input_tokens``.
        compacted_units: Content units that were compacted deterministically.
        must_preserve_units: Content units classified as must-preserve.
        must_preserve_facts: Literal facts that validation required.
        content_kinds: Number of content units per kind, such as ``json`` or
            ``log``.
        validation_status: See `ValidationStatus`.
        recovery_status: See `RecoveryStatus`.
        latency_ms: Wall-clock time spent in the middleware, in milliseconds.
    """

    summary_id: str | None
    generation: int
    thread_id: str | None
    trigger_reason: str
    input_messages: int
    input_tokens: int
    available_tokens: int
    overflow_tokens: int
    prepared_tokens: int
    output_messages: int
    output_tokens: int
    compression_ratio: float
    compacted_units: int
    must_preserve_units: int
    must_preserve_facts: int
    content_kinds: dict[str, int] = field(default_factory=dict)
    validation_status: ValidationStatus
    recovery_status: RecoveryStatus
    latency_ms: float

    def as_dict(self) -> dict[str, object]:
        """Return the event as a JSON-compatible dictionary.

        Returns:
            Every field, with ``content_kinds`` copied.
        """
        return asdict(self)
