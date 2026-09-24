"""Integration tests exercising the full IntelligentSummarizationMiddleware pipeline."""

from __future__ import annotations

import json

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage

from contextsage import IntelligentSummarizationMiddleware
from contextsage.observability.events import SummarizationEvent


def _fake_model(summary_text: str) -> GenericFakeChatModel:
    return GenericFakeChatModel(messages=iter([AIMessage(content=summary_text)]))


def _large_mixed_conversation() -> list:
    return [
        HumanMessage(content="Please process the order for customer 123.", id="h1"),
        AIMessage(content="Okay, processing customer 123.", id="a1"),
        HumanMessage(content="No, use customer 456 instead of customer 123.", id="h2"),
        ToolMessage(
            content=(
                json.dumps(
                    {
                        "status": "failed",
                        "transaction_id": "TX-991",
                        "errors": ["connection pool exhausted"],
                    }
                )
                + "\n"
                + ("INFO heartbeat ok\n" * 60)
                + "ERROR root cause: PostgreSQL connection pool exhaustion\n"
            ),
            tool_call_id="call1",
            id="t1",
        ),
        AIMessage(content="Investigating the failure now.", id="a2"),
        HumanMessage(content="Any update on the transaction?", id="h3"),
    ]


@pytest.mark.integration
def test_middleware_triggers_and_returns_valid_update():
    middleware = IntelligentSummarizationMiddleware(
        model=_fake_model("Summary: customer 456, TX-991 failed due to pool exhaustion."),
        trigger=("tokens", 50),
        keep=("messages", 2),
    )
    result = middleware.before_model({"messages": _large_mixed_conversation()}, None)
    assert result is not None
    messages = result["messages"]
    assert isinstance(messages[0], RemoveMessage)
    assert len(messages) > 1


@pytest.mark.integration
def test_middleware_does_not_trigger_below_threshold():
    middleware = IntelligentSummarizationMiddleware(
        model=_fake_model("unused"),
        trigger=("tokens", 1_000_000),
        keep=("messages", 20),
    )
    small_conversation = [HumanMessage(content="hi", id="x1"), AIMessage(content="hello", id="x2")]
    result = middleware.before_model({"messages": small_conversation}, None)
    assert result is None


@pytest.mark.integration
async def test_middleware_async_path_mirrors_sync_behavior():
    middleware = IntelligentSummarizationMiddleware(
        model=_fake_model("Summary: customer 456, TX-991 failed due to pool exhaustion."),
        trigger=("tokens", 50),
        keep=("messages", 2),
    )
    result = await middleware.abefore_model({"messages": _large_mixed_conversation()}, None)
    assert result is not None
    assert isinstance(result["messages"][0], RemoveMessage)


@pytest.mark.integration
def test_middleware_recovers_missing_facts_via_validation(monkeypatch):
    """If the LLM 'forgets' a must-preserve fact, ContextSage must restate it."""
    middleware = IntelligentSummarizationMiddleware(
        model=_fake_model("Everything is fine now."),  # deliberately loses all facts
        trigger=("tokens", 50),
        keep=("messages", 2),
    )
    result = middleware.before_model({"messages": _large_mixed_conversation()}, None)
    assert result is not None
    combined_text = "\n".join(str(getattr(m, "content", "")) for m in result["messages"])
    assert "456" in combined_text
    assert "TX-991" in combined_text


@pytest.mark.integration
def test_middleware_preserves_tool_call_pairing():
    middleware = IntelligentSummarizationMiddleware(
        model=_fake_model("Order 42 has shipped."),
        trigger=("tokens", 10),
        keep=("messages", 1),
    )
    conversation = [
        HumanMessage(content="Look up order 42.", id="h1"),
        AIMessage(
            content="",
            id="a1",
            tool_calls=[{"id": "call-42", "name": "lookup_order", "args": {"order_id": 42}}],
        ),
        ToolMessage(content="Order 42: shipped", tool_call_id="call-42", id="t1"),
        AIMessage(content="Order 42 has shipped.", id="a2"),
    ]
    result = middleware.before_model({"messages": conversation}, None)
    if result is None:
        return
    content_messages = [m for m in result["messages"] if not isinstance(m, RemoveMessage)]
    tool_call_ids = {
        call["id"]
        for m in content_messages
        for call in (getattr(m, "tool_calls", None) or [])
        if isinstance(call, dict) and "id" in call
    }
    orphaned_tool_messages = [
        m
        for m in content_messages
        if isinstance(m, ToolMessage) and m.tool_call_id not in tool_call_ids
    ]
    assert orphaned_tool_messages == []


@pytest.mark.integration
def test_middleware_invokes_observability_hook_with_populated_event():
    captured: list[SummarizationEvent] = []
    middleware = IntelligentSummarizationMiddleware(
        model=_fake_model("Summary: customer 456, TX-991 failed due to pool exhaustion."),
        trigger=("tokens", 50),
        keep=("messages", 2),
        observability_hook=captured.append,
    )
    result = middleware.before_model({"messages": _large_mixed_conversation()}, None)
    assert result is not None
    assert len(captured) == 1
    event = captured[0]
    assert "tokens" in event.trigger_reason.lower()
    assert event.input_tokens > 0
    assert event.available_tokens > 0
    assert event.selected_target_count >= 0
    assert event.validation_status in {"skipped", "passed", "failed_recovered"}
    assert event.recovery_status != "not_run"
    assert event.latency_ms >= 0.0
    assert "content" not in event.as_dict()


@pytest.mark.integration
def test_middleware_does_not_invoke_observability_hook_below_threshold():
    captured: list[SummarizationEvent] = []
    middleware = IntelligentSummarizationMiddleware(
        model=_fake_model("unused"),
        trigger=("tokens", 1_000_000),
        keep=("messages", 20),
        observability_hook=captured.append,
    )
    small_conversation = [HumanMessage(content="hi", id="x1"), AIMessage(content="hello", id="x2")]
    result = middleware.before_model({"messages": small_conversation}, None)
    assert result is None
    assert captured == []


@pytest.mark.integration
def test_middleware_observability_disabled_uses_null_hook_without_error():
    middleware = IntelligentSummarizationMiddleware(
        model=_fake_model("Summary: customer 456, TX-991 failed due to pool exhaustion."),
        trigger=("tokens", 50),
        keep=("messages", 2),
        observability_enabled=False,
    )
    result = middleware.before_model({"messages": _large_mixed_conversation()}, None)
    assert result is not None


@pytest.mark.integration
def test_middleware_emits_observability_event_on_recovery_path():
    captured: list[SummarizationEvent] = []
    middleware = IntelligentSummarizationMiddleware(
        model=_fake_model("Everything is fine now."),  # deliberately loses all facts
        trigger=("tokens", 50),
        keep=("messages", 2),
        observability_hook=captured.append,
    )
    result = middleware.before_model({"messages": _large_mixed_conversation()}, None)
    assert result is not None
    assert len(captured) == 1
    assert captured[0].recovery_status != "not_run"


@pytest.mark.integration
async def test_middleware_async_path_invokes_observability_hook():
    captured: list[SummarizationEvent] = []
    middleware = IntelligentSummarizationMiddleware(
        model=_fake_model("Summary: customer 456, TX-991 failed due to pool exhaustion."),
        trigger=("tokens", 50),
        keep=("messages", 2),
        observability_hook=captured.append,
    )
    result = await middleware.abefore_model({"messages": _large_mixed_conversation()}, None)
    assert result is not None
    assert len(captured) == 1
