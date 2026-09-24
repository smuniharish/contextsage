"""Unit tests for structured observability events and hooks."""

from __future__ import annotations

import logging

from contextsage.observability.events import (
    LoggingObservabilityHook,
    NullObservabilityHook,
    SummarizationEvent,
)


def _sample_event(**overrides: object) -> SummarizationEvent:
    defaults: dict[str, object] = {
        "trigger_reason": "tokens",
        "input_tokens": 1000,
        "available_tokens": 800,
        "overflow_tokens": 200,
        "selected_target_count": 3,
        "content_signal_counts": {"json": 2, "log": 1},
        "prepared_tokens": 700,
        "summary_tokens": 150,
        "compression_ratio": 0.15,
        "validation_status": "passed",
        "recovery_status": "none_needed",
        "fallback_used": False,
        "latency_ms": 42.5,
    }
    defaults.update(overrides)
    return SummarizationEvent(**defaults)  # type: ignore[arg-type]


def test_summarization_event_as_dict_round_trips_all_fields():
    event = _sample_event()
    payload = event.as_dict()
    assert payload["trigger_reason"] == "tokens"
    assert payload["input_tokens"] == 1000
    assert payload["available_tokens"] == 800
    assert payload["overflow_tokens"] == 200
    assert payload["selected_target_count"] == 3
    assert payload["content_signal_counts"] == {"json": 2, "log": 1}
    assert payload["prepared_tokens"] == 700
    assert payload["summary_tokens"] == 150
    assert payload["compression_ratio"] == 0.15
    assert payload["validation_status"] == "passed"
    assert payload["recovery_status"] == "none_needed"
    assert payload["fallback_used"] is False
    assert payload["latency_ms"] == 42.5


def test_summarization_event_never_carries_raw_message_content():
    """The dataclass has no field capable of holding raw message text."""
    event = _sample_event()
    payload = event.as_dict()
    assert "content" not in payload
    assert "messages" not in payload
    assert "api_key" not in payload


def test_summarization_event_defaults_are_zero_valued_when_unset():
    event = SummarizationEvent(
        trigger_reason="messages",
        input_tokens=10,
        available_tokens=10,
        overflow_tokens=0,
        selected_target_count=0,
    )
    assert event.content_signal_counts == {}
    assert event.prepared_tokens == 0
    assert event.summary_tokens == 0
    assert event.compression_ratio == 0.0
    assert event.validation_status == "not_run"
    assert event.recovery_status == "not_run"
    assert event.fallback_used is False
    assert event.latency_ms == 0.0


def test_null_observability_hook_is_a_silent_no_op():
    hook = NullObservabilityHook()
    assert hook(_sample_event()) is None


def test_logging_observability_hook_emits_one_record_with_event_payload(caplog):
    hook = LoggingObservabilityHook()
    event = _sample_event()
    with caplog.at_level(logging.INFO, logger="contextsage.observability"):
        hook(event)
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.message == "contextsage.summarization"
    assert record.levelno == logging.INFO
    assert record.contextsage == event.as_dict()  # type: ignore[attr-defined]


def test_logging_observability_hook_respects_custom_level(caplog):
    hook = LoggingObservabilityHook(level=logging.WARNING)
    with caplog.at_level(logging.WARNING, logger="contextsage.observability"):
        hook(_sample_event())
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.WARNING
