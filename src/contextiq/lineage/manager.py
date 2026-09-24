"""Summary lineage tracking.

Every summarization operation is recorded so that repeated
summarize-of-a-summary chains remain traceable rather than degrading
silently. The ``generation`` counter increases whenever the messages being
summarized already include a prior ContextIQ-produced summary.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from contextiq.core.models import SummaryLineage

CONTEXTIQ_SUMMARY_ID_PREFIX = "contextiq-summary-"


@dataclass(slots=True)
class LineageManager:
    """In-memory lineage ledger for a single middleware instance."""

    _records: dict[str, SummaryLineage] = field(default_factory=dict)

    def next_summary_id(self) -> str:
        return f"{CONTEXTIQ_SUMMARY_ID_PREFIX}{uuid.uuid4().hex[:12]}"

    def determine_generation(self, source_summary_ids: tuple[str, ...]) -> int:
        if not source_summary_ids:
            return 1
        parent_generations = [
            self._records[sid].generation for sid in source_summary_ids if sid in self._records
        ]
        return (max(parent_generations) + 1) if parent_generations else 1

    def record(
        self,
        *,
        summary_id: str,
        source_message_ids: tuple[str, ...],
        source_summary_ids: tuple[str, ...],
        input_tokens: int,
        prepared_tokens: int,
        summary_tokens: int,
        selected_target_count: int,
        preservation_unit_count: int,
        validation_status: str,
        recovery_status: str,
        fallback_used: bool,
    ) -> SummaryLineage:
        compression_ratio = summary_tokens / input_tokens if input_tokens > 0 else 0.0
        lineage = SummaryLineage(
            summary_id=summary_id,
            generation=self.determine_generation(source_summary_ids),
            source_message_ids=source_message_ids,
            source_summary_ids=source_summary_ids,
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            input_tokens=input_tokens,
            prepared_tokens=prepared_tokens,
            summary_tokens=summary_tokens,
            compression_ratio=compression_ratio,
            selected_target_count=selected_target_count,
            preservation_unit_count=preservation_unit_count,
            validation_status=validation_status,
            recovery_status=recovery_status,
            fallback_used=fallback_used,
        )
        self._records[summary_id] = lineage
        return lineage

    def get(self, summary_id: str) -> SummaryLineage | None:
        return self._records.get(summary_id)

    def all(self) -> tuple[SummaryLineage, ...]:
        return tuple(self._records.values())


def find_prior_summary_ids(message_ids: tuple[str | None, ...]) -> tuple[str, ...]:
    """Identify which of the given message ids are themselves prior ContextIQ summaries."""
    return tuple(mid for mid in message_ids if mid and mid.startswith(CONTEXTIQ_SUMMARY_ID_PREFIX))
