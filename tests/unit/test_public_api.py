from __future__ import annotations

import logging
from typing import override

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from parsefabric.compression import Tokenizer

import contextsage
from contextsage import (
    BalancedPolicy,
    CompositeEventSink,
    ConfigurationError,
    EventSink,
    FrameworkAdapter,
    JSONCompaction,
    LoggingEventSink,
    MaximumCompressionPolicy,
    MaximumPreservationPolicy,
    Message,
    OpenTelemetryEventSink,
    PreservationPolicy,
    PreservationThresholds,
    SummarizationEvent,
    TokenizerTokenCounter,
    ToolCall,
)
from contextsage.sinks import deliver


def event(**overrides: object) -> SummarizationEvent:
    values: dict[str, object] = {
        "summary_id": "s1",
        "generation": 1,
        "thread_id": "t",
        "trigger_reason": "tokens>=10",
        "input_messages": 10,
        "input_tokens": 1000,
        "available_tokens": 900,
        "overflow_tokens": 100,
        "prepared_tokens": 800,
        "output_messages": 3,
        "output_tokens": 200,
        "compression_ratio": 0.2,
        "compacted_units": 2,
        "must_preserve_units": 1,
        "must_preserve_facts": 1,
        "content_kinds": {"json": 1},
        "validation_status": "passed",
        "recovery_status": "none_needed",
        "policy": "BalancedPolicy",
        "latency_ms": 1.5,
    }
    values.update(overrides)
    return SummarizationEvent(**values)  # type: ignore[arg-type]


class Recorder(EventSink):
    def __init__(self, error: Exception | None = None) -> None:
        self.events: list[SummarizationEvent] = []
        self.calls: list[str] = []
        self.error = error

    @override
    async def emit(self, event: SummarizationEvent) -> None:
        if self.error is not None:
            raise self.error
        self.events.append(event)

    @override
    async def flush(self) -> None:
        self.calls.append("flush")
        if self.error is not None:
            raise self.error

    @override
    async def close(self) -> None:
        self.calls.append("close")
        if self.error is not None:
            raise self.error


def test_version_and_public_names():
    assert contextsage.__version__
    assert all(hasattr(contextsage, name) for name in contextsage.__all__)


def test_messages_validate_role_and_content():
    with pytest.raises(ValueError, match="role"):
        Message("bot", "x")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="content"):
        Message("user", ["x"])  # type: ignore[arg-type]


def test_native_objects_are_ignored_by_equality():
    native = object()
    message = Message("user", "x", id="1", native=native)
    assert message == Message("user", "x", id="1")
    rewritten = message.with_content("y")
    assert rewritten.content == "y"
    assert rewritten.native is native
    assert not message.is_summary


def test_preservation_thresholds_are_validated():
    with pytest.raises(ConfigurationError, match="'must'"):
        PreservationThresholds(must=1.5, should=0.1, error_must=0.1)
    with pytest.raises(ConfigurationError, match="'should'"):
        PreservationThresholds(must=0.5, should=True, error_must=0.1)  # type: ignore[arg-type]
    with pytest.raises(ConfigurationError, match="must not exceed"):
        PreservationThresholds(must=0.4, should=0.5, error_must=0.1)


def test_builtin_policies_are_ordered():
    policies = (MaximumPreservationPolicy(), BalancedPolicy(), MaximumCompressionPolicy())
    musts = [policy.thresholds.must for policy in policies]
    assert musts == sorted(musts)
    assert [policy.json_compaction for policy in policies] == [
        JSONCompaction.MINIFY,
        JSONCompaction.COLLAPSE_RUNS,
        JSONCompaction.SAMPLE,
    ]
    assert BalancedPolicy().name == "BalancedPolicy"


def test_custom_policies_subclass_the_abc():
    class Strict(PreservationPolicy):
        @property
        @override
        def thresholds(self) -> PreservationThresholds:
            return PreservationThresholds(must=0.1, should=0.05, error_must=0.1)

        @property
        @override
        def json_compaction(self) -> JSONCompaction:
            return JSONCompaction.MINIFY

        @property
        @override
        def name(self) -> str:
            return "strict"

    assert Strict().name == "strict"
    with pytest.raises(TypeError):
        PreservationPolicy()  # type: ignore[abstract]


def test_framework_adapters_convert_whole_histories():
    class Strings(FrameworkAdapter[str]):
        @override
        def to_message(self, native: str) -> Message:
            return Message("user", native, native=native)

        @override
        def from_message(self, message: Message) -> str:
            return message.content

    adapter = Strings()
    assert adapter.propagated_errors == ()
    assert adapter.from_messages(adapter.to_messages(["a", "b"])) == ["a", "b"]


async def test_token_counter_counts_content_names_and_tool_calls():
    counter = TokenizerTokenCounter(tokens_per_message=0)
    plain = await counter.count([Message("assistant", "abcd")])
    called = await counter.count(
        [Message("assistant", "abcd", name="agent", tool_calls=(ToolCall("c", "t", {"q": 1}),))]
    )
    assert plain == 1
    assert called > plain
    assert await counter.count([]) == 0
    assert counter.tokenizer is not None


async def test_token_counter_cache_is_bounded_and_optional():
    class Counting(Tokenizer):
        def __init__(self) -> None:
            self.calls = 0

        @override
        async def count(self, text: str) -> int:
            self.calls += 1
            return len(text)

    tokenizer = Counting()
    counter = TokenizerTokenCounter(tokenizer, tokens_per_message=1, cache_size=1)
    messages = [Message("user", "ab"), Message("user", "abc")]
    assert await counter.count(messages) == 7
    assert await counter.count(messages[1:]) == 4
    assert tokenizer.calls == 2
    uncached = TokenizerTokenCounter(tokenizer, cache_size=0)
    await uncached.count(messages[:1])
    await uncached.count(messages[:1])
    assert tokenizer.calls == 4


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"tokenizer": object()}, "tokenizer"),
        ({"tokens_per_message": -1}, "tokens_per_message"),
        ({"cache_size": True}, "cache_size"),
    ],
)
def test_token_counter_rejects_invalid_arguments(arguments, message):
    with pytest.raises(ConfigurationError, match=message):
        TokenizerTokenCounter(**arguments)


async def test_logging_sink_writes_one_structured_record(caplog):
    caplog.set_level(logging.INFO, logger="contextsage")
    await LoggingEventSink().emit(event())
    (record,) = caplog.records
    assert record.getMessage() == "contextsage summarization"
    assert record.contextsage["summary_id"] == "s1"  # type: ignore[attr-defined]
    with pytest.raises(ConfigurationError, match="logger"):
        LoggingEventSink("contextsage")  # type: ignore[arg-type]


async def test_opentelemetry_sink_records_every_instrument():
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    sink = OpenTelemetryEventSink(provider.get_meter("test"))
    await sink.emit(event())
    data = reader.get_metrics_data()
    assert data is not None
    names = {
        metric.name
        for resource in data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
    }
    assert names == {
        "contextsage.summarizations",
        "contextsage.input_tokens",
        "contextsage.output_tokens",
        "contextsage.compression_ratio",
        "contextsage.compacted_units",
        "contextsage.duration",
    }
    provider.shutdown()
    await OpenTelemetryEventSink().emit(event())


async def test_composite_sink_isolates_failing_children(caplog):
    good, bad = Recorder(), Recorder(RuntimeError("down"))
    composite = CompositeEventSink([bad, good])
    assert composite.sinks == (bad, good)
    await composite.emit(event())
    assert len(good.events) == 1
    assert "event sink Recorder failed" in caplog.text
    with pytest.raises(ExceptionGroup) as raised:
        await composite.flush()
    assert len(raised.value.exceptions) == 1
    with pytest.raises(ExceptionGroup):
        await composite.close()
    assert good.calls == ["flush", "close"]
    await CompositeEventSink([good]).close()
    with pytest.raises(ConfigurationError, match="EventSink"):
        CompositeEventSink([object()])  # type: ignore[list-item]


async def test_default_sink_hooks_do_nothing():
    class Minimal(EventSink):
        @override
        async def emit(self, event: SummarizationEvent) -> None:
            raise RuntimeError("boom")

    sink = Minimal()
    await sink.flush()
    await sink.close()
    await deliver(sink, event())


def test_events_are_content_free_dictionaries():
    record = event().as_dict()
    assert record["content_kinds"] == {"json": 1}
    assert record["policy"] == "BalancedPolicy"
