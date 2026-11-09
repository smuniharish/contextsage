from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, override

import pytest
from agxai import InMemoryProvenanceStore, MemoryOperation, ProvenanceLink
from parsefabric.builtins import CodeDetector
from parsefabric.execution import AsyncExecutionBackend, ExecutionBackend

from contextsage import (
    DEFAULT_IDENTIFIER_PATTERNS,
    ConfigurationError,
    ContextSageError,
    ContextSummarizer,
    EventSink,
    MaximumCompressionPolicy,
    Message,
    ParsingOptions,
    SummarizationEvent,
    create_agxai_runtime,
)
from tests.support.builders import (
    FailingModel,
    FakeModel,
    assistant,
    incident_history,
    system,
    tool,
    user,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from agxai import CanonicalEvent, Execution
    from parsefabric import LanguageModel


class Sink(EventSink):
    def __init__(self, error: Exception | None = None) -> None:
        self.events: list[SummarizationEvent] = []
        self.calls: list[str] = []
        self.error = error

    @override
    async def emit(self, event: SummarizationEvent) -> None:
        self.events.append(event)

    @override
    async def flush(self) -> None:
        self.calls.append("flush")
        if self.error is not None:
            raise self.error

    @override
    async def close(self) -> None:
        self.calls.append("close")


class Backend(AsyncExecutionBackend):
    def __init__(self, error: Exception | None = None) -> None:
        super().__init__()
        self.error = error
        self.shutdowns = 0

    @override
    async def run(self, function: Callable[..., Any], /, *args: object, **kwargs: object) -> Any:
        if self.error is not None:
            raise self.error
        return await super().run(function, *args, **kwargs)

    @override
    async def shutdown(self) -> None:
        self.shutdowns += 1


class BrokenDetector(CodeDetector):
    languages = ("python",)

    @override
    async def prepare(self) -> None:
        raise OSError("offline")

    @override
    async def detect(self, text: str) -> str | None:
        return None


class BrokenStore(InMemoryProvenanceStore):
    @override
    async def write(self, item: Execution | ProvenanceLink | CanonicalEvent) -> None:
        raise RuntimeError("database down")


def chat(count: int) -> list[Message]:
    return [user(f"hello number {index}", id=f"m{index}") for index in range(count)]


def summarizer(
    model: LanguageModel | None = None,
    *,
    backend: ExecutionBackend | None = None,
    **arguments: Any,
) -> ContextSummarizer:
    arguments.setdefault("trigger", ("messages", 4))
    arguments.setdefault("keep", ("messages", 2))
    arguments.setdefault("sink", Sink())
    return ContextSummarizer(
        model or FakeModel(),
        parsing=ParsingOptions(code_detector=None, backend=backend or Backend()),
        **arguments,
    )


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"policy": object()}, "policy"),
        ({"token_counter": object()}, "token_counter"),
        ({"parsing": object()}, "parsing"),
        ({"sink": object()}, "sink"),
        ({"runtime": object()}, "runtime"),
        ({"summary_prompt": "no placeholder"}, "summary_prompt"),
        ({"trim_tokens_to_summarize": 0}, "trim_tokens_to_summarize"),
        ({"trim_tokens_to_summarize": True}, "trim_tokens_to_summarize"),
        ({"identifier_patterns": ["INC-\\d+"]}, "identifier_patterns"),
        ({"identifier_patterns": [re.compile(b"x")]}, "identifier_patterns"),
        ({"propagate_errors": ValueError}, "propagate_errors"),
        ({"propagate_errors": [int]}, "propagate_errors"),
        ({"validation_enabled": 1}, "validation_enabled"),
    ],
)
def test_invalid_arguments_are_rejected(arguments, message):
    with pytest.raises(ConfigurationError, match=message):
        ContextSummarizer(FakeModel(), **arguments)


def test_model_must_be_a_language_model():
    with pytest.raises(ConfigurationError, match=r"parsefabric\.LanguageModel"):
        ContextSummarizer(object())  # type: ignore[arg-type]


async def test_defaults_are_created_and_closed():
    engine = ContextSummarizer(FakeModel())
    assert engine.policy.name == "BalancedPolicy"
    assert type(engine.sink).__name__ == "LoggingEventSink"
    assert engine.runtime.application_id == "contextsage"
    await engine.prepare()
    await engine.aclose()
    await engine.aclose()


async def test_history_below_the_trigger_is_left_alone():
    model = FakeModel()
    async with summarizer(model) as engine:
        assert await engine.summarize(chat(3)) is None
    assert model.requests == []


async def test_old_messages_are_summarized_and_recent_ones_kept():
    sink = Sink()
    model = FakeModel("They greeted each other.")
    async with summarizer(model, sink=sink) as engine:
        result = await engine.summarize([system(), *chat(5)], thread_id="t1")
    assert result is not None
    first, summary, *kept = result.messages
    assert first.role == "system"
    assert summary.is_summary
    assert summary.lineage is not None
    assert summary.lineage.generation == 1
    assert summary.id == summary.lineage.summary_id
    assert "They greeted each other." in summary.content
    assert [message.id for message in kept] == ["m3", "m4"]
    assert result.event.validation_status == "passed"
    assert result.event.recovery_status == "none_needed"
    assert result.event.thread_id == "t1"
    assert sink.events == [result.event]
    (request,) = model.requests
    assert "hello number 0" in request[0].content
    assert "hello number 4" not in request[0].content


async def test_lineage_links_every_summarized_message():
    async with summarizer() as engine:
        result = await engine.summarize(chat(5), thread_id="t1")
        assert result is not None
        summary_id = result.event.summary_id
        assert summary_id is not None
        links = await engine.lineage(summary_id, thread_id="t1")
        assert {link.source_id for link in links} == {"m0", "m1", "m2"}
        assert await engine.lineage(summary_id, thread_id="other") == ()


async def test_summaries_of_summaries_increase_the_generation():
    async with summarizer() as engine:
        first = await engine.summarize(chat(5), thread_id="t")
        assert first is not None
        history = [*first.messages, *chat(8)[5:]]
        second = await engine.summarize(history, thread_id="t")
    assert second is not None
    summary = second.messages[0]
    assert summary.lineage is not None
    assert summary.lineage.generation == 2
    assert summary.lineage.source_summary_ids == (first.event.summary_id,)
    assert second.event.generation == 2


async def test_missing_facts_are_restated_and_carried_forward():
    async with summarizer(keep=("messages", 1)) as engine:
        result = await engine.summarize(incident_history(), thread_id="t")
        assert result is not None
        assert result.event.validation_status == "failed_recovered"
        assert result.event.recovery_status == "restated_facts"
        text = "\n".join(message.content for message in result.messages)
        assert "INC-9931" in text
        summary = next(message for message in result.messages if message.is_summary)
        assert summary.lineage is not None
        assert summary.lineage.facts
        later = await engine.summarize([*result.messages, *chat(4)], thread_id="t")
    assert later is not None
    assert "INC-9931" in "\n".join(message.content for message in later.messages)


async def test_validation_can_be_disabled():
    async with summarizer(validation_enabled=False, keep=("messages", 1)) as engine:
        result = await engine.summarize(incident_history())
    assert result is not None
    assert result.event.validation_status == "disabled"
    assert "INC-9931" not in "\n".join(message.content for message in result.messages)


async def test_orphaned_tool_results_are_reported(caplog):
    history = [*chat(4), tool("late result", call="gone", id="t9")]
    async with summarizer() as engine:
        result = await engine.summarize(history)
    assert result is not None
    assert result.event.validation_status == "failed_unrecovered"
    assert result.event.recovery_status == "none_applicable"
    assert "without their tool call" in caplog.text


async def test_compaction_alone_still_rewrites_the_history():
    async with summarizer(
        keep=("messages", 50), trigger=("messages", 2), policy=MaximumCompressionPolicy()
    ) as engine:
        result = await engine.summarize(incident_history())
        disabled = summarizer(
            keep=("messages", 50),
            trigger=("messages", 2),
            policy=MaximumCompressionPolicy(),
            validation_enabled=False,
        )
        async with disabled:
            unvalidated = await disabled.summarize(incident_history())
    assert result is not None
    assert result.event.summary_id is None
    assert result.event.generation == 0
    assert result.event.compacted_units > 0
    assert result.event.validation_status == "passed"
    assert not any(message.is_summary for message in result.messages)
    assert unvalidated is not None
    assert unvalidated.event.validation_status == "disabled"


async def test_nothing_to_summarize_or_compact_returns_none():
    async with summarizer(keep=("messages", 50)) as engine:
        assert await engine.summarize(chat(5)) is None


async def test_summary_prompt_and_trimming_are_applied():
    model = FakeModel()
    async with summarizer(
        model, summary_prompt="Condense:\n{messages}", trim_tokens_to_summarize=None
    ) as engine:
        await engine.summarize(chat(5))
    (request,) = model.requests
    assert request[0].content.startswith("Condense:\n")
    assert "hello number 0" in request[0].content


@pytest.mark.parametrize("model", [FakeModel("   "), FailingModel()])
async def test_model_failures_fall_back_to_trimming(model, caplog):
    async with summarizer(model) as engine:
        result = await engine.summarize(chat(6))
    assert result is not None
    assert result.event.validation_status == "skipped"
    assert result.event.recovery_status == "trimmed_fallback"
    assert [message.id for message in result.messages] == ["m4", "m5"]
    assert result.event.summary_id is None
    assert "trimming to the keep window" in caplog.text


async def test_fallback_keeps_missing_facts_in_a_summary():
    async with summarizer(FailingModel(), keep=("messages", 1)) as engine:
        result = await engine.summarize(incident_history(), thread_id="t")
        assert result is not None
        summary_id = result.event.summary_id
        assert summary_id is not None
        assert result.messages[0].is_summary
        assert await engine.lineage(summary_id, thread_id="t")


async def test_propagated_errors_are_re_raised():
    class InterruptError(Exception):
        pass

    async with summarizer(
        FailingModel(InterruptError()), propagate_errors=[InterruptError]
    ) as engine:
        with pytest.raises(InterruptError):
            await engine.summarize(chat(5))


async def test_analysis_failure_summarizes_unanalyzed(caplog):
    async with summarizer(backend=Backend(RuntimeError("worker died"))) as engine:
        result = await engine.summarize(chat(5))
    assert result is not None
    assert result.event.must_preserve_facts == 0
    assert "could not analyze the history" in caplog.text


async def test_missing_grammars_degrade_or_fail_fast(caplog):
    options = ParsingOptions(code_detector=BrokenDetector(), backend=Backend())
    async with ContextSummarizer(
        FakeModel(), trigger=("messages", 4), keep=("messages", 2), parsing=options, sink=Sink()
    ) as engine:
        with pytest.raises(ConfigurationError, match="offline"):
            await engine.prepare()
        caplog.set_level(logging.WARNING, logger="contextsage")
        assert await engine.summarize(chat(5)) is not None
    assert "continuing without code detection" in caplog.text


async def test_non_messages_are_rejected():
    async with summarizer() as engine:
        with pytest.raises(TypeError, match=r"contextsage\.Message"):
            await engine.summarize(["hello"])  # type: ignore[list-item]


async def test_closed_summarizer_refuses_work():
    engine = summarizer()
    await engine.aclose()
    with pytest.raises(ContextSageError, match="closed"):
        await engine.summarize(chat(5))


async def test_provided_resources_are_flushed_not_closed():
    sink, backend = Sink(), Backend()
    runtime = create_agxai_runtime()
    engine = summarizer(sink=sink, backend=backend, runtime=runtime)
    await engine.summarize(chat(5))
    await engine.aclose()
    assert sink.calls == ["flush"]
    assert backend.shutdowns == 0
    assert engine.runtime is runtime
    await runtime.close()


async def test_owned_resources_are_closed():
    sink = Sink()
    engine = ContextSummarizer(FakeModel(), trigger=("messages", 4), keep=("messages", 2))
    await engine.summarize(chat(5))
    await engine.aclose()
    owned = ContextSummarizer(FakeModel(), sink=sink)
    await owned.aclose()
    assert sink.calls == ["flush"]


async def test_close_failures_are_grouped():
    engine = summarizer(sink=Sink(RuntimeError("flush failed")))
    with pytest.raises(ExceptionGroup) as raised:
        await engine.aclose()
    assert str(raised.value.exceptions[0]) == "flush failed"


async def test_summaries_are_recorded_as_memory_writes_of_the_active_run():
    runtime = create_agxai_runtime()
    async with summarizer(runtime=runtime) as engine:
        run = await runtime.start_run({"configurable": {"thread_id": "t"}})
        with runtime.activate_run(run):
            result = await engine.summarize(chat(5), thread_id="t")
        await runtime.finish_run(run)
    assert result is not None
    (memory,) = run.execution.memory
    assert memory.memory_id == result.event.summary_id
    assert memory.operation is MemoryOperation.WRITE
    assert memory.namespace == "contextsage"
    await runtime.close()


async def test_provenance_failures_never_interrupt_summarization(caplog):
    runtime = create_agxai_runtime(store=BrokenStore())
    async with summarizer(runtime=runtime) as engine:
        result = await engine.summarize(chat(5))
    assert result is not None
    assert "could not record provenance" in caplog.text
    await runtime.close()


async def test_events_never_contain_message_content():
    secret = "the launch code is 0000-SECRET"
    history = [user(secret, id="x"), *chat(4)]
    async with summarizer() as engine:
        result = await engine.summarize(history)
    assert result is not None
    assert secret not in repr(result.event.as_dict())


async def test_custom_identifier_patterns_become_facts():
    pattern = re.compile(r"\bORD-\d{6}\b")
    history = [
        user("Track order ORD-123456 please.", id="o1"),
        assistant("Tracking.", id="o2"),
        *chat(4),
    ]
    async with summarizer(identifier_patterns=[*DEFAULT_IDENTIFIER_PATTERNS, pattern]) as engine:
        result = await engine.summarize(history)
    assert result is not None
    assert "ORD-123456" in "\n".join(message.content for message in result.messages)
