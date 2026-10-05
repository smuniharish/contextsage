"""Run ContextSage inside a live agent loop.

Run: python examples/live_agent.py

Requires CONTEXTSAGE_LLM_API_KEY (and optionally CONTEXTSAGE_LLM_BASE_URL and
CONTEXTSAGE_LLM_MODEL); see .env.example. The agent calls a tool that returns a
large diagnostics report. Before the next model call, ContextSage compacts the
report inside the agent loop, keeping the incident, the error and the
transaction ID, and the model answers from the compacted context.
"""

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from _models import live_model
from contextsage import IntelligentSummarizationMiddleware, SummarizationEvent


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


model = live_model()
events: list[SummarizationEvent] = []
agent = create_agent(
    model=model,
    tools=[incident_report],
    system_prompt="You are an SRE assistant. Use the tools to investigate incidents.",
    middleware=[
        IntelligentSummarizationMiddleware(
            model=model,
            trigger=("tokens", 2_000),
            keep=("messages", 6),
            observability_hook=events.append,
        )
    ],
)
result = agent.invoke(
    {"messages": [HumanMessage("Investigate INC-9931: what is the root cause?")]}
)

print("Answer:", result["messages"][-1].text)
for event in events:
    print(
        f"summarization: {event.input_tokens} -> {event.output_tokens} tokens, "
        f"{event.compacted_units} units compacted, validation {event.validation_status}"
    )
