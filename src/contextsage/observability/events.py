"""Structured observability.

Every summarization operation can emit a single structured event carrying
only aggregate, non-sensitive fields (token counts, ratios, statuses). Raw
message content, tool outputs, and API keys are never included by default.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Protocol

logger = logging.getLogger("contextsage.observability")


@dataclass(slots=True)
class SummarizationEvent:
    """A single structured observability record for one middleware invocation."""

    trigger_reason: str
    input_tokens: int
    available_tokens: int
    overflow_tokens: int
    selected_target_count: int
    content_signal_counts: dict[str, int] = field(default_factory=dict)
    prepared_tokens: int = 0
    summary_tokens: int = 0
    compression_ratio: float = 0.0
    validation_status: str = "not_run"
    recovery_status: str = "not_run"
    fallback_used: bool = False
    latency_ms: float = 0.0

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class ObservabilityHook(Protocol):
    """Implemented by anything that wants to receive :class:`SummarizationEvent`."""

    def __call__(self, event: SummarizationEvent) -> None: ...


class LoggingObservabilityHook:
    """Default hook: emits one structured, redacted log line per operation."""

    def __init__(self, level: int = logging.INFO) -> None:
        self._level = level

    def __call__(self, event: SummarizationEvent) -> None:
        logger.log(self._level, "contextsage.summarization", extra={"contextsage": event.as_dict()})


class NullObservabilityHook:
    """No-op hook used when ``observability_enabled=False``."""

    def __call__(self, event: SummarizationEvent) -> None:
        return None
