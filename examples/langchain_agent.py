"""Add ContextSage to a LangChain agent.

Run: python examples/langchain_agent.py

Requires the ``langchain`` extra: ``pip install "contextsage[langchain]"``.
`IntelligentSummarizationMiddleware` runs before every model call of a
``create_agent`` agent. Here the agent calls a tool whose large report pushes
the history past the trigger; before the next model call, ContextSage
compacts the report, the summary model summarizes the older messages, and the
agent answers from the rewritten history. The summary model can differ from
the agent's model, for example a smaller and cheaper one.
"""

from __future__ import annotations

import asyncio
import json

from _langchain_shared import scripted_chat_model
from _shared import EventCollector, first_line
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import tool

from contextsage.integrations.langchain import LINEAGE_KEY, IntelligentSummarizationMiddleware


def is_summary(message: BaseMessage) -> bool:
    """Whether ``message`` is a summary written by ContextSage."""
    return LINEAGE_KEY in message.additional_kwargs


@tool
def incident_report(incident_id: str) -> str:
    """Return the diagnostics report for an incident."""
    log = "".join(
        f"2026-10-04T03:{index // 60:02d}:{index % 60:02d}Z INFO payments-worker processing queue\n"
        for index in range(200)
    )
    return (
        f"Incident {incident_id}: elevated latency on the payments service.\n"
        + json.dumps({"orders": [{"status": "queued"}] * 40, "region": "eu-west-1"})
        + "\n"
        + log
        + "2026-10-04T04:00:00Z ERROR connection pool exhausted for TX-991\n"
    )


async def main() -> None:
    agent_model = scripted_chat_model(
        AIMessage(
            "",
            tool_calls=[
                {"id": "call-1", "name": "incident_report", "args": {"incident_id": "INC-9931"}}
            ],
        ),
        "INC-9931 is caused by connection pool exhaustion while settling TX-991.",
    )
    summary_model = scripted_chat_model(
        "The user asked to investigate the payments outage INC-9931; the incident "
        "report shows transaction TX-991 failing on a saturated connection pool."
    )
    sink = EventCollector()
    middleware = IntelligentSummarizationMiddleware(
        summary_model, trigger=("tokens", 2_000), keep=("messages", 2), sink=sink
    )
    agent = create_agent(model=agent_model, tools=[incident_report], middleware=[middleware])
    try:
        result = await agent.ainvoke(
            {"messages": [HumanMessage("Investigate the payments outage INC-9931.")]}
        )
    finally:
        await middleware.aclose()

    print("History after the agent turn:")
    for message in result["messages"]:
        calls = ", ".join(call["name"] for call in getattr(message, "tool_calls", []))
        text = message.text.partition("\n\n")[2] if is_summary(message) else message.text
        print(f"  {message.type:<5} {first_line(text) or f'calls {calls}'}")
    event = sink.events[0]
    print()
    print(f"tokens: {event.input_tokens} -> {event.output_tokens}")
    print(f"validation: {event.validation_status}, must-keep facts: {event.must_preserve_facts}")


if __name__ == "__main__":
    asyncio.run(main())
