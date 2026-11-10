"""Use ContextSage on one agent of a multi-agent swarm.

Run: python examples/swarm.py

Requires CONTEXTSAGE_LLM_API_KEY (and optionally CONTEXTSAGE_LLM_BASE_URL and
CONTEXTSAGE_LLM_MODEL); see the repository's .env.example. A triage agent
hands the conversation to an investigator whose tool returns a large report;
only the investigator runs ContextSage, and the swarm keeps its state in a
checkpointer across turns.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from _shared import EventCollector, chat_model
from langchain.agents import create_agent
from langchain.agents.middleware import ModelRequest, ModelResponse, wrap_model_call
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph_swarm import create_handoff_tool, create_swarm

from contextsage.integrations.langchain import IntelligentSummarizationMiddleware

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


@wrap_model_call
async def without_speaker_names(
    request: ModelRequest, handler: Callable[[ModelRequest], Awaitable[ModelResponse]]
) -> ModelResponse:
    """Drop the agent name stamped on messages by swarm agents.

    Some OpenAI-compatible endpoints accept ``name`` only on tool messages.
    """
    messages = [
        message
        if isinstance(message, ToolMessage) or message.name is None
        else message.model_copy(update={"name": None})
        for message in request.messages
    ]
    return await handler(request.override(messages=messages))


@tool
def billing_records(account: str) -> str:
    """Return recent billing records for an account."""
    rows = "".join(
        f"2026-10-0{1 + index % 3}T08:00:{index % 60:02d}Z INFO invoice batch {account} ok\n"
        for index in range(300)
    )
    return (
        f"Billing records for {account}.\n{rows}"
        "2026-10-04T08:59:59Z ERROR invoice INV-8812 charged twice for account "
        f"{account}\n"
    )


async def main() -> None:
    async with chat_model() as model:
        sink = EventCollector()
        middleware = IntelligentSummarizationMiddleware(
            model, trigger=("tokens", 2_000), keep=("messages", 6), sink=sink
        )
        triage = create_agent(
            model,
            tools=[
                create_handoff_tool(
                    agent_name="investigator",
                    description="Hand billing questions to the investigator.",
                )
            ],
            system_prompt="You triage support requests. Hand billing questions over.",
            name="triage",
            middleware=[without_speaker_names],
        )
        investigator = create_agent(
            model,
            tools=[billing_records],
            system_prompt="You investigate billing problems with the billing_records tool.",
            name="investigator",
            middleware=[middleware, without_speaker_names],
        )
        swarm = create_swarm([triage, investigator], default_active_agent="triage").compile(
            checkpointer=InMemorySaver()
        )
        config = {"configurable": {"thread_id": "billing-1"}}
        try:
            result = await swarm.ainvoke(
                {"messages": [HumanMessage("Account ACC-42 was charged twice. Why?")]}, config
            )
        finally:
            await middleware.aclose()

    print("Answer:", result["messages"][-1].text)
    for event in sink.events:
        print(
            f"summarization in thread {event.thread_id}: "
            f"{event.input_tokens} -> {event.output_tokens} tokens"
        )


if __name__ == "__main__":
    asyncio.run(main())
