from __future__ import annotations

import asyncio
import itertools
from types import SimpleNamespace
from typing import Any, override

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    ChatMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphBubbleUp
from parsefabric import ChatMessage as PromptMessage
from parsefabric.execution import AsyncExecutionBackend

from contextsage import ConfigurationError, Message, ParsingOptions, SummaryLineage, ToolCall
from contextsage.integrations.langchain import (
    IntelligentSummarizationMiddleware,
    LangChainAdapter,
    LangChainSummaryModel,
    LangChainTokenCounter,
)

SUMMARY = "SUMMARY-TEXT the user said hello several times."
ADAPTER = LangChainAdapter()


def fake(text: str = SUMMARY, **fields: Any) -> GenericFakeChatModel:
    return GenericFakeChatModel(messages=itertools.repeat(AIMessage(content=text)), **fields)


class Failing(GenericFakeChatModel):
    error: Any = None

    @override
    async def _agenerate(self, *args: Any, **kwargs: Any) -> Any:
        raise self.error


def middleware(model: Any = None, **arguments: Any) -> IntelligentSummarizationMiddleware:
    arguments.setdefault("trigger", ("messages", 4))
    arguments.setdefault("keep", ("messages", 2))
    return IntelligentSummarizationMiddleware(
        model if model is not None else fake(),
        parsing=ParsingOptions(code_detector=None, backend=AsyncExecutionBackend()),
        **arguments,
    )


def history(count: int) -> list[AnyMessage]:
    return [HumanMessage(content=f"hello number {index}", id=f"m{index}") for index in range(count)]


def runtime(thread_id: str | None = "t1") -> Any:
    return SimpleNamespace(
        execution_info=SimpleNamespace(thread_id=thread_id),
        server_info=SimpleNamespace(graph_id="graph"),
    )


def test_adapter_converts_every_role():
    natives = [
        SystemMessage(content="rules", id="s"),
        HumanMessage(content="hi", id="h", name="ann"),
        AIMessage(
            content="",
            id="a",
            tool_calls=[{"id": "c1", "name": "search", "args": {"q": 1}, "type": "tool_call"}],
        ),
        ToolMessage(content="found", id="t", tool_call_id="c1"),
        ChatMessage(content="dev", role="developer", id="d"),
        ChatMessage(content="odd", role="narrator", id="n"),
    ]
    messages = ADAPTER.to_messages(natives)
    assert [message.role for message in messages] == [
        "system",
        "user",
        "assistant",
        "tool",
        "system",
        "user",
    ]
    assert messages[1].name == "ann"
    assert messages[2].tool_calls[0].arguments == {"q": 1}
    assert messages[3].tool_call_id == "c1"
    assert ADAPTER.from_messages(messages) == natives
    assert all(
        rebuilt is native
        for rebuilt, native in zip(ADAPTER.from_messages(messages), natives, strict=True)
    )


def test_adapter_creates_native_messages_for_new_messages():
    created = ADAPTER.from_messages(
        [
            Message("system", "rules", id="s"),
            Message("user", "hi", id="h"),
            Message("assistant", "ok", tool_calls=(ToolCall("c1", "search", {"q": 1}),)),
            Message("tool", "r", tool_call_id="c1"),
        ]
    )
    assert [type(message) for message in created] == [
        SystemMessage,
        HumanMessage,
        AIMessage,
        ToolMessage,
    ]
    assert created[3].tool_call_id == "c1"  # type: ignore[attr-defined]


def test_adapter_rewrites_content_and_marks_summaries():
    native = HumanMessage(content="old", id="h", additional_kwargs={"keep": True})
    rewritten = ADAPTER.from_message(ADAPTER.to_message(native).with_content("new"))
    assert rewritten.content == "new"
    assert rewritten.additional_kwargs == {"keep": True}
    lineage = SummaryLineage(summary_id="h", generation=2)
    stamped = Message("user", "summary", id="h", lineage=lineage, native=native)
    summary = ADAPTER.from_message(stamped)
    assert summary.additional_kwargs["lc_source"] == "summarization"
    assert summary.additional_kwargs["keep"] is True
    restored = ADAPTER.to_message(summary)
    assert restored.lineage == lineage
    fresh = ADAPTER.from_message(Message("user", "summary", id="x", lineage=lineage))
    assert isinstance(fresh, HumanMessage)
    assert ADAPTER.to_message(fresh).lineage == lineage


def test_langchain_summaries_are_read_as_first_generation_summaries():
    native = HumanMessage(
        content="Here is a summary", id="old", additional_kwargs={"lc_source": "summarization"}
    )
    message = ADAPTER.to_message(native)
    assert message.lineage is not None
    assert message.lineage.summary_id == "old"
    assert message.lineage.generation == 1


def test_non_text_content_is_never_rewritten():
    native = HumanMessage(
        content=[{"type": "text", "text": "see"}, {"type": "image", "url": "https://x/y.png"}]
    )
    message = ADAPTER.to_message(native)
    assert message.content == "see"
    assert not message.rewritable


def test_adapter_propagates_langgraph_control_flow():
    assert ADAPTER.propagated_errors == (GraphBubbleUp,)


async def test_summary_model_wraps_a_chat_model():
    chat = fake("done")
    model = LangChainSummaryModel(chat)
    assert model.model is chat
    assert model.name == "langchain:GenericFakeChatModel"
    assert await model.complete([PromptMessage("user", "summarize")]) == "done"


def test_summary_model_reads_the_context_window_from_the_profile():
    assert LangChainSummaryModel(fake(profile={"max_input_tokens": 1000})).max_input_tokens == 1000
    assert LangChainSummaryModel(fake(profile={"max_input_tokens": 0})).max_input_tokens is None
    assert LangChainSummaryModel(fake()).max_input_tokens is None


def test_summary_model_accepts_model_identifiers(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    assert LangChainSummaryModel("openai:gpt-5-mini").name == "langchain:ChatOpenAI"
    with pytest.raises(ConfigurationError, match="cannot initialize model"):
        LangChainSummaryModel("no-such-provider:model")
    with pytest.raises(ConfigurationError, match="BaseChatModel"):
        LangChainSummaryModel(object())  # type: ignore[arg-type]


async def test_token_counter_uses_the_counting_function():
    counter = LangChainTokenCounter(len)
    assert await counter.count([Message("user", "a"), Message("user", "b")]) == 2
    assert await LangChainTokenCounter().count([Message("user", "hello " * 40)]) > 10
    with pytest.raises(ConfigurationError, match="callable"):
        LangChainTokenCounter(42)  # type: ignore[arg-type]


async def test_middleware_configuration():
    with pytest.raises(ConfigurationError, match="LangChainAdapter"):
        IntelligentSummarizationMiddleware(fake(), adapter=object())  # type: ignore[arg-type]
    sized = middleware(fake(profile={"max_input_tokens": 50_000}))
    assert sized.summarizer._budget.maximum_context_tokens == 50_000
    explicit = middleware(fake(profile={"max_input_tokens": 50_000}), maximum_context_tokens=9000)
    assert explicit.summarizer._budget.maximum_context_tokens == 9000
    await sized.aclose()
    await explicit.aclose()


async def test_before_model_replaces_the_history():
    hook = middleware()
    assert await hook.abefore_model({"messages": history(3)}, runtime()) is None
    update = await hook.abefore_model({"messages": history(5)}, runtime())
    assert update is not None
    removal, summary, *kept = update["messages"]
    assert removal.id == "__remove_all__"
    assert summary.additional_kwargs["lc_source"] == "summarization"
    assert [message.id for message in kept] == ["m3", "m4"]
    links = await hook.alineage(summary.id, thread_id="t1")
    assert {link.source_id for link in links} == {"m0", "m1", "m2"}
    await hook.aclose()


def test_synchronous_hook_runs_on_a_private_loop():
    hook = middleware()
    update = hook.before_model({"messages": history(5)}, runtime(None))
    assert update is not None
    assert hook.before_model({"messages": history(2)}, runtime(None)) is None
    asyncio.run(hook.aclose())
    asyncio.run(hook.aclose())


async def test_graph_control_flow_is_never_swallowed():
    hook = middleware(Failing(messages=iter(()), error=GraphBubbleUp()))
    with pytest.raises(GraphBubbleUp):
        await hook.abefore_model({"messages": history(5)}, runtime())
    fallback = middleware(Failing(messages=iter(()), error=RuntimeError("down")))
    update = await fallback.abefore_model({"messages": history(5)}, runtime())
    assert update is not None
    assert [message.id for message in update["messages"][1:]] == ["m3", "m4"]
    await hook.aclose()
    await fallback.aclose()


def agent(hook: IntelligentSummarizationMiddleware) -> Any:
    return create_agent(
        model=GenericFakeChatModel(messages=itertools.repeat(AIMessage(content="final answer"))),
        middleware=[hook],
        checkpointer=InMemorySaver(),
    )


async def test_agent_history_is_summarized_and_checkpointed():
    hook = middleware()
    graph = agent(hook)
    config = {"configurable": {"thread_id": "agent-thread"}}
    result = await graph.ainvoke({"messages": history(5)}, config)
    summary, *rest = result["messages"]
    assert summary.additional_kwargs["lc_source"] == "summarization"
    assert [message.id for message in rest[:2]] == ["m3", "m4"]
    assert rest[-1].content == "final answer"
    links = await hook.alineage(summary.id, thread_id="agent-thread")
    assert {link.source_id for link in links} == {"m0", "m1", "m2"}
    state = await graph.aget_state(config)
    assert state.values["messages"][0].id == summary.id
    await hook.aclose()


@pytest.mark.filterwarnings("ignore:The v3 streaming protocol")
async def test_summary_model_calls_are_hidden_or_tagged_in_streams():
    hook = middleware()
    graph = agent(hook)
    run = await graph.astream_events(
        {"messages": history(5)}, {"configurable": {"thread_id": "v3"}}, version="v3"
    )
    async with run:
        texts = [await stream.text async for stream in run.messages]
    assert SUMMARY not in texts
    assert "final answer" in texts
    tagged = [
        chunk.content
        async for chunk, metadata in graph.astream(
            {"messages": history(5)},
            {"configurable": {"thread_id": "legacy"}},
            stream_mode="messages",
        )
        if metadata.get("lc_source") == "summarization"
    ]
    assert "".join(str(content) for content in tagged) == SUMMARY
    await hook.aclose()


def test_synchronous_agents_are_supported():
    hook = middleware()
    result = agent(hook).invoke({"messages": history(5)}, {"configurable": {"thread_id": "sync"}})
    assert result["messages"][0].additional_kwargs["lc_source"] == "summarization"
    asyncio.run(hook.aclose())
