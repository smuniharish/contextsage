"""End-to-end checks against a real OpenAI-compatible chat model.

Deselected by default; run them with ``pytest -m live``. They need the
``CONTEXTSAGE_LLM_*`` environment variables, or a ``.env`` file, described in
``.env.example``, and are skipped without them.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, override

import pytest
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from contextsage import ContextSummarizer, EventSink, SummarizationEvent
from contextsage.integrations.langchain import (
    IntelligentSummarizationMiddleware,
    LangChainAdapter,
    LangChainSummaryModel,
)
from tests.support.builders import NO_CODE, heartbeat_log

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from langchain_openai import ChatOpenAI

pytestmark = pytest.mark.live


class Events(EventSink):
    def __init__(self) -> None:
        self.events: list[SummarizationEvent] = []

    @override
    async def emit(self, event: SummarizationEvent) -> None:
        self.events.append(event)


@pytest.fixture
async def model() -> AsyncIterator[ChatOpenAI]:
    pytest.importorskip("dotenv").load_dotenv()
    api_key = os.environ.get("CONTEXTSAGE_LLM_API_KEY")
    if not api_key:
        pytest.skip("CONTEXTSAGE_LLM_API_KEY is not set")
    from langchain_openai import ChatOpenAI

    chat = ChatOpenAI(
        api_key=api_key,
        base_url=os.environ.get("CONTEXTSAGE_LLM_BASE_URL") or None,
        model=os.environ.get("CONTEXTSAGE_LLM_MODEL") or "gpt-5-mini",
    )
    yield chat
    await chat.root_async_client.close()


def history() -> list[BaseMessage]:
    return [
        HumanMessage("Settle order ORD-4410 for customer 123.", id="h1"),
        AIMessage("", id="a1", tool_calls=[{"id": "c1", "name": "settlement_log", "args": {}}]),
        ToolMessage(
            heartbeat_log(200)
            + "2026-10-04T09:00:00Z ERROR settlement TX-7781 failed: card declined\n",
            tool_call_id="c1",
            id="t1",
        ),
        HumanMessage("No, use customer 456 instead of customer 123.", id="h2"),
        AIMessage("Understood.", id="a2"),
        HumanMessage("What should we try next?", id="h3"),
    ]


async def test_a_real_summary_keeps_every_fact(model):
    sink = Events()
    adapter = LangChainAdapter()
    async with ContextSummarizer(
        LangChainSummaryModel(model),
        trigger=("messages", 6),
        keep=("messages", 1),
        parsing=NO_CODE,
        sink=sink,
    ) as summarizer:
        result = await summarizer.summarize(adapter.to_messages(history()), thread_id="live")
    assert result is not None
    text = "\n".join(message.content for message in result.messages)
    for fact in ("ORD-4410", "TX-7781", "456"):
        assert fact in text
    (event,) = sink.events
    assert event.summary_id is not None
    assert event.validation_status in {"passed", "failed_recovered"}
    assert event.output_tokens < event.input_tokens


async def test_a_real_agent_answers_from_the_compacted_context(model):
    @tool
    def settlement_log(order_id: str) -> str:
        """Return the settlement log of an order."""
        return (
            f"Settlement log for {order_id}.\n"
            + heartbeat_log(300)
            + "2026-10-04T09:00:00Z ERROR settlement TX-7781 failed: card declined\n"
        )

    sink = Events()
    middleware = IntelligentSummarizationMiddleware(
        model,
        trigger=("tokens", 1_500),
        keep=("messages", 6),
        parsing=NO_CODE,
        sink=sink,
    )
    agent = create_agent(
        model=model,
        tools=[settlement_log],
        system_prompt="Use the settlement_log tool to investigate orders.",
        middleware=[middleware],
    )
    result = await agent.ainvoke(
        {"messages": [HumanMessage("Why did settlement of ORD-4410 fail?")]}
    )
    await middleware.aclose()
    assert result["messages"][-1].text
    assert sink.events
    assert all(event.validation_status != "failed_unrecovered" for event in sink.events)
    assert any(event.compacted_units for event in sink.events)
