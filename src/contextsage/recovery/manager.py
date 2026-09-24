"""Recovery manager.

Recovery is staged and deliberately conservative: it never blindly retries
an expensive LLM summarization call (the wrapped LangGraph middleware
already retries transient errors internally up to three times via
``Runnable.with_retry()``). Instead:

* If the LLM summarization step itself failed (timeout, rate limit,
  malformed response after retries), ContextSage falls back to a purely
  deterministic trim: keep the most recent messages and prepend an
  explicit, literal "preserved facts" message so no ``MUST_PRESERVE``
  information is silently lost.
* If validation failed (a required fact went missing from an otherwise
  successful summary), ContextSage appends a literal "preserved facts"
  message alongside the produced summary rather than re-invoking the LLM.

Either way, recovery never corrupts state: it only ever *adds* explicit,
literal information back, and always returns messages that keep tool-call
pairing valid.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage

from contextsage.core.models import RecoveryOutcome, ValidationResult

if TYPE_CHECKING:
    from collections.abc import Sequence

    from langchain_core.messages import BaseMessage

_PRESERVED_FACTS_HEADER = (
    "The following facts were flagged as must-preserve by ContextSage and are "
    "restated here verbatim to guarantee they were not lost during "
    "summarization:"
)


class RecoveryManager:
    """Implements ContextSage's staged, fail-safe recovery strategies."""

    def build_preserved_facts_message(self, facts: tuple[str, ...]) -> AIMessage:
        bullet_list = "\n".join(f"- {fact}" for fact in facts)
        return AIMessage(
            id=f"contextsage-recovery-{uuid.uuid4().hex[:8]}",
            content=f"{_PRESERVED_FACTS_HEADER}\n{bullet_list}",
        )

    def recover_from_validation_failure(
        self,
        *,
        messages: list[BaseMessage],
        validation_result: ValidationResult,
        must_preserve_facts: tuple[str, ...],
    ) -> tuple[list[BaseMessage], RecoveryOutcome]:
        missing_facts = tuple(
            f.fact for f in validation_result.critical_findings if f.fact is not None
        )
        facts_to_restate = missing_facts or must_preserve_facts
        if not facts_to_restate:
            return messages, RecoveryOutcome(
                recovered=False,
                strategy="none_applicable",
                detail="validation failed but no literal facts were identified to restate",
            )
        recovered_messages = [*messages, self.build_preserved_facts_message(facts_to_restate)]
        return recovered_messages, RecoveryOutcome(
            recovered=True,
            strategy="append_preserved_facts",
            fallback_used=True,
            detail=f"restated {len(facts_to_restate)} fact(s) verbatim",
        )

    def recover_from_summarization_failure(
        self,
        *,
        original_messages: Sequence[BaseMessage],
        keep_count: int,
        must_preserve_facts: tuple[str, ...],
        error: Exception,
    ) -> tuple[list[BaseMessage], RecoveryOutcome]:
        kept = original_messages[-keep_count:] if keep_count > 0 else list(original_messages)
        recovered_messages: list[BaseMessage] = list(kept)
        if must_preserve_facts:
            recovered_messages = [
                self.build_preserved_facts_message(must_preserve_facts),
                *recovered_messages,
            ]
        return recovered_messages, RecoveryOutcome(
            recovered=True,
            strategy="deterministic_trim_fallback",
            fallback_used=True,
            detail=f"LLM summarization failed ({error}); fell back to deterministic trim",
        )
