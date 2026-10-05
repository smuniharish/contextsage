"""End-to-end checks against a real OpenAI-compatible chat model.

Deselected by default; run them with ``pytest -m live``. They need the
``CONTEXTSAGE_LLM_*`` environment variables, or a ``.env`` file, described in
``.env.example``, and are skipped without them.
"""

from __future__ import annotations

import os

import pytest
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.runtime import Runtime

from contextsage import IntelligentSummarizationMiddleware, SummarizationEvent
from tests.support.builders import heartbeat_log

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def model():
    pytest.importorskip("dotenv").load_dotenv()
    if not os.environ.get("CONTEXTSAGE_LLM_API_KEY"):
        pytest.skip("CONTEXTSAGE_LLM_API_KEY is not set")
    from _models import live_model

    return live_model()


@pytest.fixture
async def async_model(model):
    yield model
    # langchain-openai shares one async HTTP client per process; close it on
    # this test's event loop rather than leave it to the garbage collector.
    await model.root_async_client.close()


def history() -> list[AnyMessage]:
    return [
        HumanMessage("Settle order ORD-4410 for customer 123."),
        AIMessage("", tool_calls=[{"id": "c1", "name": "settlement_log", "args": {}}]),
        ToolMessage(
            heartbeat_log(200)
            + "2026-10-04T09:00:00Z ERROR settlement TX-7781 failed: card declined\n",
            tool_call_id="c1",
        ),
        HumanMessage("No, use customer 456 instead of customer 123."),
        AIMessage("Understood."),
        HumanMessage("What should we try next?"),
    ]


async def test_a_real_summary_keeps_every_fact(async_model):
    events: list[SummarizationEvent] = []
    middleware = IntelligentSummarizationMiddleware(
        model=async_model,
        trigger=("messages", 6),
        keep=("messages", 1),
        observability_hook=events.append,
    )
    update = await middleware.abefore_model({"messages": history()}, Runtime())
    assert update is not None
    text = "\n".join(message.text for message in update["messages"][1:])
    for fact in ("ORD-4410", "TX-7781", "456"):
        assert fact in text
    (event,) = events
    assert event.summary_id is not None
    assert event.validation_status in {"passed", "failed_recovered"}
    assert event.output_tokens < event.input_tokens


def test_a_real_agent_answers_from_the_compacted_context(model):
    @tool
    def settlement_log(order_id: str) -> str:
        """Return the settlement log of an order."""
        return (
            f"Settlement log for {order_id}.\n"
            + heartbeat_log(300)
            + "2026-10-04T09:00:00Z ERROR settlement TX-7781 failed: card declined\n"
        )

    events: list[SummarizationEvent] = []
    agent = create_agent(
        model=model,
        tools=[settlement_log],
        system_prompt="Use the settlement_log tool to investigate orders.",
        middleware=[
            IntelligentSummarizationMiddleware(
                model=model,
                trigger=("tokens", 1_500),
                keep=("messages", 6),
                observability_hook=events.append,
            )
        ],
    )
    result = agent.invoke(
        {"messages": [HumanMessage("Why did settlement of ORD-4410 fail?")]}
    )
    assert result["messages"][-1].text
    assert events
    assert all(event.validation_status != "failed_unrecovered" for event in events)
    assert any(event.compacted_units for event in events)
