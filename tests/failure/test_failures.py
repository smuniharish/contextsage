from __future__ import annotations

import logging
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage
from langgraph.errors import GraphInterrupt
from langgraph.runtime import Runtime
from langgraph_xai import InMemoryProvenanceStore

from contextsage import IntelligentSummarizationMiddleware, SummarizationEvent
from contextsage._pipeline.decomposition import Decomposer
from contextsage._pipeline.recovery import FALLBACK_NOTICE
from contextsage._pipeline.summarizer import Summarizer
from contextsage._pipeline.validation import orphaned_tool_results
from tests.support.builders import (
    FailingModel,
    incident_history,
    state,
    summary_model,
)


def build(
    model, **options: Any
) -> tuple[IntelligentSummarizationMiddleware, list[SummarizationEvent]]:
    events: list[SummarizationEvent] = []
    options.setdefault("trigger", ("tokens", 100))
    options.setdefault("keep", ("messages", 2))
    options.setdefault("code_languages", ())
    instance = IntelligentSummarizationMiddleware(
        model, observability_hook=events.append, **options
    )
    return instance, events


def body(update: dict[str, Any] | None) -> list:
    assert update is not None
    assert isinstance(update["messages"][0], RemoveMessage)
    return update["messages"][1:]


def test_summary_model_failure_falls_back_to_a_valid_trimmed_history(caplog):
    instance, events = build(FailingModel())
    with caplog.at_level(logging.WARNING, logger="contextsage"):
        messages = body(instance.before_model(state(incident_history()), Runtime()))
    assert "summary model failed (RuntimeError)" in caplog.text
    notice = messages[0]
    assert notice.type == "human"
    assert notice.text.startswith(FALLBACK_NOTICE)
    for fact in ("INC-9931", "TX-991"):
        assert fact in notice.text
    assert [message.id for message in messages[1:]] == ["a3", "h3"]
    assert orphaned_tool_results(messages) == ()
    (event,) = events
    assert (event.validation_status, event.recovery_status) == (
        "skipped",
        "trimmed_fallback",
    )
    assert event.summary_id == notice.id
    assert event.generation == 1


async def test_async_summary_model_failure_falls_back():
    store = InMemoryProvenanceStore()
    instance, events = build(FailingModel(), provenance_store=store)
    messages = body(await instance.abefore_model(state(incident_history()), Runtime()))
    assert messages[0].text.startswith(FALLBACK_NOTICE)
    summary_id = events[0].summary_id
    assert summary_id is not None
    links = await instance.alineage(summary_id)
    assert {str(link.source_id) for link in links} >= {"h1", "t1", "h2"}


def test_fallback_without_facts_or_a_summary_message():
    instance, events = build(FailingModel(), keep=("messages", 2))
    history = [
        HumanMessage("hello there " * 30, id="h1"),
        AIMessage("hi " * 30, id="a1"),
        HumanMessage("how are you", id="h2"),
        AIMessage("fine", id="a2"),
    ]
    messages = body(instance.before_model(state(history), Runtime()))
    assert [message.id for message in messages] == ["h2", "a2"]
    assert events[0].summary_id is None
    assert events[0].generation == 0


def test_graph_interrupts_are_not_swallowed(monkeypatch):
    def interrupt(self, messages, runtime):
        raise GraphInterrupt(())

    monkeypatch.setattr(Summarizer, "summarize", interrupt)
    instance, _ = build(summary_model())
    with pytest.raises(GraphInterrupt):
        instance.before_model(state(incident_history()), Runtime())


async def test_graph_interrupts_are_not_swallowed_async(monkeypatch):
    async def interrupt(self, messages, runtime):
        raise GraphInterrupt(())

    monkeypatch.setattr(Summarizer, "asummarize", interrupt)
    instance, _ = build(summary_model())
    with pytest.raises(GraphInterrupt):
        await instance.abefore_model(state(incident_history()), Runtime())


def orphaning(self, messages, runtime):
    return [
        HumanMessage("summary", additional_kwargs={"lc_source": "summarization"}),
        ToolMessage("dangling", tool_call_id="ghost", id="g"),
    ]


def test_orphaned_tool_results_are_reported(monkeypatch, caplog):
    monkeypatch.setattr(Summarizer, "summarize", orphaning)
    instance, events = build(summary_model())
    history = [HumanMessage("hello " * 120, id="h1"), AIMessage("hi", id="a1")]
    instance.before_model(state(history), Runtime())
    assert "without their tool call after summarization: ghost" in caplog.text
    assert (events[0].validation_status, events[0].recovery_status) == (
        "failed_unrecovered",
        "none_applicable",
    )


def test_missing_facts_and_orphans_are_both_handled(monkeypatch):
    monkeypatch.setattr(Summarizer, "summarize", orphaning)
    instance, events = build(summary_model())
    messages = body(instance.before_model(state(incident_history()), Runtime()))
    assert "INC-9931" in messages[0].text
    assert (events[0].validation_status, events[0].recovery_status) == (
        "failed_unrecovered",
        "restated_facts",
    )


def test_analysis_failures_degrade_to_plain_summarization(monkeypatch, caplog):
    async def broken(self, messages):
        raise RuntimeError("parser crashed")

    monkeypatch.setattr(Decomposer, "decompose", broken)
    instance, events = build(summary_model("Plain summary."))
    with caplog.at_level(logging.ERROR, logger="contextsage"):
        messages = body(instance.before_model(state(incident_history()), Runtime()))
    assert "could not analyze the history" in caplog.text
    assert "Plain summary." in messages[0].text
    assert (events[0].must_preserve_facts, events[0].compacted_units) == (0, 0)
    assert events[0].validation_status == "passed"


async def test_analysis_failures_degrade_async(monkeypatch):
    async def broken(self, messages):
        raise RuntimeError("parser crashed")

    monkeypatch.setattr(Decomposer, "decompose", broken)
    instance, events = build(summary_model("Plain summary."))
    update = await instance.abefore_model(state(incident_history()), Runtime())
    assert "Plain summary." in body(update)[0].text
    assert events[0].content_kinds == {}


def test_provenance_store_failures_do_not_break_summarization(caplog):
    class BrokenStore(InMemoryProvenanceStore):
        async def write(self, item: object) -> None:
            raise ConnectionError("database unavailable")

    instance, events = build(summary_model(), provenance_store=BrokenStore())
    assert instance.before_model(state(incident_history()), Runtime()) is not None
    assert "could not record provenance" in caplog.text
    assert len(events) == 1
