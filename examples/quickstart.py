"""Add ContextSage to a LangChain agent and watch it summarize a long history.

Run: python examples/quickstart.py

The agent starts from a history whose large tool result pushes it past the
trigger. Before the next model call, ContextSage compacts the repetitive log
and JSON in that result, LangChain writes the summary, and ContextSage checks
that the incident and transaction IDs survived.
"""

import json

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from _models import first_line, scripted_model
from contextsage import IntelligentSummarizationMiddleware, SummarizationEvent

events: list[SummarizationEvent] = []

middleware = IntelligentSummarizationMiddleware(
    model=scripted_model(
        "The payments outage INC-9931 was traced to transaction TX-991 and a "
        "saturated connection pool."
    ),
    trigger=("tokens", 2_000),
    keep=("messages", 2),
    observability_hook=events.append,
)

agent = create_agent(
    model=scripted_model("INC-9931 only affects the payments service."),
    tools=[],
    middleware=[middleware],
)

log = "".join(
    f"2026-10-04T03:{index // 60:02d}:{index % 60:02d}Z INFO payments-worker "
    "processing queue\n"
    for index in range(200)
)
report = (
    "Incident INC-9931: elevated latency on the payments service.\n"
    + json.dumps({"orders": [{"status": "queued"}] * 40, "region": "eu-west-1"})
    + "\n"
    + log
    + "2026-10-04T04:00:00Z ERROR connection pool exhausted for TX-991\n"
)
history = [
    HumanMessage("Investigate the payments outage."),
    AIMessage("", tool_calls=[{"id": "call-1", "name": "incident_report", "args": {}}]),
    ToolMessage(report, tool_call_id="call-1"),
    AIMessage("INC-9931 is caused by connection pool exhaustion."),
    HumanMessage("Is any other service affected?"),
]

result = agent.invoke({"messages": history})

print("History after the agent turn:")
for message in result["messages"]:
    print(f"  {message.type:<5} {first_line(message.text)}")

event = events[0]
print()
print(f"tokens before:      {event.input_tokens}")
print(f"after compaction:   {event.prepared_tokens}")
print(f"after summary:      {event.output_tokens}")
print(f"compression ratio:  {event.compression_ratio:.3f}")
print(f"validation:         {event.validation_status}")
print(f"must-keep facts:    {event.must_preserve_facts}")
