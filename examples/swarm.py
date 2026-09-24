"""``langgraph_swarm`` multi-agent integration example.

Two named agents built with ``create_agent`` (one specialized "triage"
agent, one specialized "incident" agent that owns
``IntelligentSummarizationMiddleware``) are combined into a single swarm
via ``create_swarm``. A handoff tool lets the triage agent transfer control
to the incident specialist, entirely via real LLM tool-calling — nothing in
this example is pre-scripted.

Two real, checkpointed turns are invoked against the compiled swarm:

1. The user asks for the incident specialist and to investigate an
   escalation; the model calls the real handoff tool, control transfers to
   the incident agent, which calls a real tool returning a large, log-heavy
   report -- inflating the conversation enough that
   ``IntelligentSummarizationMiddleware`` (attached only to the incident
   agent) compresses it before the agent's own final answer.
2. A follow-up question is invoked in the same thread; the swarm's
   persisted ``active_agent`` state routes it directly back to the incident
   agent, which answers from the now-compressed history.

Run with:

    python examples/swarm.py

Requires a real API key: copy .env.example to .env and set EXPLABS_API_KEY.
Requires the `examples` extra (`pip install -e ".[examples]"`) for `langgraph-swarm`.
"""

from __future__ import annotations

from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver
from langgraph_swarm import create_handoff_tool, create_swarm

from _llm import build_demo_model
from contextiq import IntelligentSummarizationMiddleware
from contextiq.observability.events import SummarizationEvent

TICKET_ID = "ESC-3390"


class EventCollector:
    """Collects emitted events to prove summarization ran inside the
    incident agent's subgraph as part of the real swarm run."""

    def __init__(self) -> None:
        self.events: list[SummarizationEvent] = []

    def __call__(self, event: SummarizationEvent) -> None:
        self.events.append(event)


def get_escalation_report() -> str:
    """Real tool the incident agent calls to fetch escalation details."""
    log_lines = "\n".join(
        f"2024-10-01T09:{minute:02d}:00 INFO auth-worker-{minute % 4} handling request"
        for minute in range(250)
    )
    return (
        f"Escalation {TICKET_ID} opened: users intermittently unable to log in, "
        "traced to expired signing keys not being rotated automatically.\n"
        f"{log_lines}\n"
        "2024-10-01T09:59:00 ERROR auth: signing key rotation job crashed silently"
    )


def build_swarm_app(events: EventCollector):
    incident_middleware = IntelligentSummarizationMiddleware(
        model=build_demo_model(),
        trigger=("tokens", 500),
        keep=("messages", 2),
        observability_hook=events,
    )

    triage_agent = create_agent(
        model=build_demo_model(),
        tools=[
            create_handoff_tool(
                agent_name="Incident",
                description="Transfer to the incident specialist for escalation investigations.",
            )
        ],
        system_prompt=(
            "You are Triage, a support front-desk assistant. For anything "
            "involving an escalation or incident investigation, transfer to "
            "the Incident agent immediately."
        ),
        name="Triage",
    )

    incident_agent = create_agent(
        model=build_demo_model(),
        tools=[get_escalation_report],
        system_prompt=(
            "You are Incident, an escalation specialist. Call "
            "get_escalation_report to investigate, then answer concisely, "
            "always citing the escalation id."
        ),
        middleware=[incident_middleware],
        name="Incident",
    )

    workflow = create_swarm([triage_agent, incident_agent], default_active_agent="Triage")
    return workflow.compile(checkpointer=InMemorySaver())


def main() -> None:
    events = EventCollector()
    app = build_swarm_app(events)
    config = {"configurable": {"thread_id": "swarm-example-1"}}

    turn_1 = app.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "I need the incident specialist to investigate the "
                        "login escalation and tell me the root cause."
                    ),
                }
            ]
        },
        config,
    )
    print("=== Turn 1 (triage -> handoff -> incident agent + tool call) ===")
    for message in turn_1["messages"]:
        content = str(getattr(message, "content", ""))[:200]
        print(f"  [{type(message).__name__}] {content}")

    turn_2 = app.invoke(
        {"messages": [{"role": "user", "content": "How many users were affected, roughly?"}]},
        config,
    )
    print()
    print("=== Turn 2 (same thread, routed straight back to the incident agent) ===")
    for message in turn_2["messages"][len(turn_1["messages"]) :]:
        content = str(getattr(message, "content", ""))[:200]
        print(f"  [{type(message).__name__}] {content}")

    combined_text = "\n".join(str(getattr(m, "content", "")) for m in turn_2["messages"])
    print()
    print("Active agent stayed on Incident across turns:", turn_2.get("active_agent") == "Incident")
    print("Summarization triggered inside the real swarm run:", len(events.events) > 0)
    print(f"{TICKET_ID} preserved despite compression:", TICKET_ID in combined_text)
    for i, event in enumerate(events.events, start=1):
        print(f"  event {i}: trigger_reason={event.trigger_reason!r}")
        print(
            f"  event {i}: compression_ratio={round(event.compression_ratio, 4)} "
            f"validation_status={event.validation_status!r}"
        )


if __name__ == "__main__":
    main()
