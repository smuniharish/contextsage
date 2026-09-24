"""``deepagents.create_deep_agent`` integration example.

``deepagents`` builds a more capable agent than ``create_agent`` (its own
built-in planning/filesystem middleware, subagent support, etc.), but
``IntelligentSummarizationMiddleware`` plugs in exactly the same way: pass
it in ``middleware=[...]`` alongside whatever else the deep agent adds.

Same two-turn structure as ``examples/agent_create_agent.py``: a large,
pre-seeded tool result inflates the history, then a real follow-up question
is invoked against the compiled deep agent, exercising the middleware
inside deepagents' own (larger) graph.

Run with:

    python examples/deep_agent.py

Requires a real API key: copy .env.example to .env and set EXPLABS_API_KEY.
Requires the `examples` extra (`pip install -e ".[examples]"`) for `deepagents`.
"""

from __future__ import annotations

from deepagents import create_deep_agent
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from _llm import build_demo_model
from contextsage import IntelligentSummarizationMiddleware
from contextsage.observability.events import SummarizationEvent

TICKET_ID = "ESC-7741"


class EventCollector:
    """Collects emitted events to prove summarization ran inside deepagents'
    own compiled graph, not just via a direct middleware call."""

    def __init__(self) -> None:
        self.events: list[SummarizationEvent] = []

    def __call__(self, event: SummarizationEvent) -> None:
        self.events.append(event)


def get_escalation_report() -> str:
    """A real tool the deep agent could call for escalation details.

    Not invoked directly in this example (the first turn is pre-seeded for
    determinism), but registered so the agent's own tool-calling path is
    exercised like a normal deployment.
    """
    log_lines = "\n".join(
        f"2024-09-01T05:{minute:02d}:00 INFO checkout-worker-{minute % 5} handling request"
        for minute in range(250)
    )
    return (
        f"Escalation {TICKET_ID} opened: checkout API returning HTTP 500 for "
        "roughly 3% of requests since the last release.\n"
        f"{log_lines}\n"
        "2024-09-01T05:59:00 ERROR checkout: unhandled null pointer in discount calculation"
    )


def main() -> None:
    events = EventCollector()
    middleware = IntelligentSummarizationMiddleware(
        model=build_demo_model(),
        trigger=("tokens", 500),
        keep=("messages", 2),
        observability_hook=events,
    )

    agent = create_deep_agent(
        model=build_demo_model(),
        tools=[get_escalation_report],
        system_prompt=(
            "You are a support engineering assistant. Answer questions about "
            "escalations using the conversation history already available to you."
        ),
        middleware=[middleware],
    )

    # Turn 1 (pre-seeded): a tool already returned a large, log-heavy report.
    history = [
        HumanMessage(content="Can you look into the checkout escalation?"),
        AIMessage(
            content="",
            tool_calls=[{"id": "call-1", "name": "get_escalation_report", "args": {}}],
        ),
        ToolMessage(content=get_escalation_report(), tool_call_id="call-1"),
        AIMessage(content=f"Found it: {TICKET_ID}, a null pointer in discount calculation."),
        # Turn 2 (real): the compiled deep agent answers this live.
        HumanMessage(content="What's the customer impact, in one sentence?"),
    ]

    result = agent.invoke({"messages": history})

    print("Final agent messages:")
    for message in result["messages"]:
        content = str(getattr(message, "content", ""))[:200]
        print(f"  [{type(message).__name__}] {content}")

    combined_text = "\n".join(str(getattr(m, "content", "")) for m in result["messages"])
    print()
    print("Summarization triggered inside the real deep-agent run:", len(events.events) > 0)
    print(f"{TICKET_ID} preserved despite compression:", TICKET_ID in combined_text)
    if events.events:
        event = events.events[0]
        print("  trigger_reason:", event.trigger_reason)
        print("  compression_ratio:", round(event.compression_ratio, 4))


if __name__ == "__main__":
    main()
