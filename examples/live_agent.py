"""Run ContextSage inside a live agent loop.

Run: python examples/live_agent.py

Requires CONTEXTSAGE_LLM_API_KEY (and optionally CONTEXTSAGE_LLM_BASE_URL and
CONTEXTSAGE_LLM_MODEL); see the repository's .env.example. The agent calls a
tool that returns a large diagnostics report. Before the next model call,
ContextSage compacts the report inside the agent loop, keeping the incident,
the error and the transaction ID, and the model answers from the compacted
context.
"""

from __future__ import annotations

import asyncio

from _shared import EventCollector, chat_model
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from contextsage.integrations.langchain import IntelligentSummarizationMiddleware


@tool
def incident_report(incident_id: str) -> str:
    """Return the diagnostics report for an incident."""
    heartbeats = "".join(
        f"2026-10-04T03:{index // 60:02d}:{index % 60:02d}Z "
        f"INFO payments-worker-{index % 3} processing queue\n"
        for index in range(400)
    )
    return (
        f"Incident {incident_id}: elevated latency on the payments service.\n"
        f"{heartbeats}"
        "2026-10-04T03:59:58Z ERROR connection pool exhausted while settling TX-991\n"
    )


async def main() -> None:
    async with chat_model() as model:
        sink = EventCollector()
        middleware = IntelligentSummarizationMiddleware(
            model,
            trigger=("tokens", 2_000),
            keep=("messages", 6),
            sink=sink,
        )
        agent = create_agent(
            model=model,
            tools=[incident_report],
            system_prompt="You are an SRE assistant. Use the tools to investigate incidents.",
            middleware=[middleware],
        )
        try:
            result = await agent.ainvoke(
                {"messages": [HumanMessage("Investigate INC-9931: what is the root cause?")]}
            )
        finally:
            await middleware.aclose()

    print("Answer:", result["messages"][-1].text)
    for event in sink.events:
        print(
            f"summarization: {event.input_tokens} -> {event.output_tokens} tokens, "
            f"{event.compacted_units} units compacted, validation {event.validation_status}"
        )


if __name__ == "__main__":
    asyncio.run(main())
