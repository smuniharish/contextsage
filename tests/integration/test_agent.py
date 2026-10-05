from __future__ import annotations

from itertools import cycle

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from contextsage import IntelligentSummarizationMiddleware, SummarizationEvent

MARKER = "RAW-SUMMARY-MODEL-OUTPUT"


def agent_with(events: list[SummarizationEvent]):
    middleware = IntelligentSummarizationMiddleware(
        GenericFakeChatModel(messages=cycle([AIMessage(MARKER)])),
        trigger=("messages", 4),
        keep=("messages", 2),
        code_languages=(),
        observability_hook=events.append,
    )
    agent = create_agent(
        model=GenericFakeChatModel(messages=cycle([AIMessage("agent answer")])),
        tools=[],
        middleware=[middleware],
        checkpointer=InMemorySaver(),
    )
    return agent, middleware


HISTORY = [
    HumanMessage("Why did TX-991 fail?"),
    AIMessage("Checking the payment logs."),
    HumanMessage("Any news?"),
    AIMessage("Still looking."),
    HumanMessage("Please summarize."),
]


def test_summarizes_inside_a_compiled_agent_with_a_checkpointer():
    events: list[SummarizationEvent] = []
    agent, _ = agent_with(events)
    config = {"configurable": {"thread_id": "support-thread"}}
    result = agent.invoke({"messages": list(HISTORY)}, config)
    messages = result["messages"]
    assert messages[0].id == events[0].summary_id
    assert messages[-1].text == "agent answer"
    assert events[0].thread_id == "support-thread"
    stored = agent.get_state(config).values["messages"]
    assert stored[0].id == events[0].summary_id


async def test_async_agent_records_thread_scoped_provenance():
    events: list[SummarizationEvent] = []
    agent, middleware = agent_with(events)
    config = {"configurable": {"thread_id": "async-thread"}}
    await agent.ainvoke({"messages": list(HISTORY)}, config)
    summary_id = events[0].summary_id
    assert summary_id is not None
    links = await middleware.alineage(summary_id, thread_id="async-thread")
    assert len(links) == 3
    assert await middleware.alineage(summary_id) == ()


@pytest.mark.filterwarnings(
    "ignore::langchain_core._api.beta_decorator.LangChainBetaWarning"
)
def test_summary_model_output_stays_out_of_streamed_messages():
    events: list[SummarizationEvent] = []
    agent, _ = agent_with(events)
    run = agent.stream_events(
        {"messages": list(HISTORY)},
        {"configurable": {"thread_id": "stream-thread"}},
        version="v3",
    )
    streamed = [str(stream.output.content) for stream in run.messages]
    assert events, "summarization should have run"
    assert not any(text == MARKER or f"'{MARKER}'" in text for text in streamed)
    assert any("agent answer" in text for text in streamed)
