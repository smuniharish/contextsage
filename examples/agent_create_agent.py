"""``langchain.agents.create_agent`` integration example.

Unlike the other examples (which call ``middleware.before_model`` directly),
this one compiles a *real* LangGraph agent via ``create_agent`` and invokes
it end-to-end across two turns:

1. A first turn's tool call produces a large, log-heavy incident report
   (pre-seeded here for determinism, exactly like a real tool would return
   it).
2. A second, real follow-up question is invoked against the compiled agent.
   Its ``before_model`` middleware hook runs *inside the real agent loop* on
   the full accumulated history, compresses the log-heavy first tool result
   while preserving the incident id, and the model then produces a genuine
   answer to the follow-up question from the compressed context.

Run with:

    python examples/agent_create_agent.py

Requires a real API key: copy .env.example to .env and set EXPLABS_API_KEY.
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from _llm import build_demo_model
from contextsage import IntelligentSummarizationMiddleware
from contextsage.observability.events import SummarizationEvent

INCIDENT_ID = "INC-9931"


class EventCollector:
    """Collects emitted events so we can prove summarization happened
    *inside* the compiled graph's own execution loop, not just when called
    directly."""

    def __init__(self) -> None:
        self.events: list[SummarizationEvent] = []

    def __call__(self, event: SummarizationEvent) -> None:
        self.events.append(event)


def get_service_incident_report() -> str:
    """A real tool the agent can call to fetch an incident report.

    Not invoked in this example (the first turn's result is pre-seeded for
    determinism), but registered on the agent so the graph's tool-calling
    path is exercised like a normal deployment.
    """
    log_lines = "\n".join(
        f"2024-08-01T03:{minute:02d}:00 INFO payments-worker-{minute % 3} processing queue"
        for minute in range(250)
    )
    return (
        f"Incident {INCIDENT_ID} opened: elevated latency on the payments service "
        "starting 03:00 UTC, root cause traced to a saturated connection pool.\n"
        f"{log_lines}\n"
        "2024-08-01T03:59:00 ERROR connection pool exhausted, failing over to replica"
    )


def main() -> None:
    events = EventCollector()
    middleware = IntelligentSummarizationMiddleware(
        model=build_demo_model(),
        trigger=("tokens", 300),
        keep=("messages", 2),
        observability_hook=events,
    )

    agent = create_agent(
        model=build_demo_model(),
        tools=[get_service_incident_report],
        system_prompt=(
            "You are an SRE assistant. Answer questions about incidents using "
            "the conversation history already available to you."
        ),
        middleware=[middleware],
    )

    # Turn 1 (pre-seeded): a tool already returned a large, log-heavy report.
    history = [
        HumanMessage(content="Can you investigate the payments outage?"),
        AIMessage(
            content="",
            tool_calls=[{"id": "call-1", "name": "get_service_incident_report", "args": {}}],
        ),
        ToolMessage(content=get_service_incident_report(), tool_call_id="call-1"),
        AIMessage(content=f"Found it: {INCIDENT_ID}, caused by connection pool exhaustion."),
        # Turn 2 (real): the compiled agent answers this live.
        HumanMessage(content="Is this incident affecting any other services?"),
    ]

    result = agent.invoke({"messages": history})

    print("Final agent messages:")
    for message in result["messages"]:
        content = str(getattr(message, "content", ""))[:200]
        print(f"  [{type(message).__name__}] {content}")

    combined_text = "\n".join(str(getattr(m, "content", "")) for m in result["messages"])
    print()
    print("Summarization triggered inside the real agent run:", len(events.events) > 0)
    print(f"{INCIDENT_ID} preserved despite compression:", INCIDENT_ID in combined_text)
    if events.events:
        event = events.events[0]
        print("  trigger_reason:", event.trigger_reason)
        print("  compression_ratio:", round(event.compression_ratio, 4))


if __name__ == "__main__":
    main()
