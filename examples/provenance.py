"""Trace a summary of a summary back to the original messages.

Run: python examples/provenance.py

Every summary is linked to the messages it replaced in a langgraph-xai
provenance store (in memory here; use a durable ProvenanceStore in
production). After two rounds of summarization, the lineage of the latest
summary reaches back through the first summary to the original messages.
"""

import asyncio

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langgraph.runtime import Runtime

from _models import scripted_model
from contextsage import IntelligentSummarizationMiddleware, SummarizationEvent

events: list[SummarizationEvent] = []
middleware = IntelligentSummarizationMiddleware(
    model=scripted_model("Summary of the shipment discussion."),
    trigger=("messages", 5),
    keep=("messages", 2),
    observability_hook=events.append,
)


def turn(index: int) -> list[AnyMessage]:
    """One question about a shipment and its answer."""
    return [
        HumanMessage(
            f"Question {index} about shipment SHP-{index:03d}.", id=f"user-{index}"
        ),
        AIMessage(f"Answer {index}.", id=f"assistant-{index}"),
    ]


def summarize(history: list[AnyMessage]) -> list[AnyMessage]:
    """Run the middleware once and return the history the model would see."""
    update = middleware.before_model({"messages": history}, Runtime())
    if update is None:
        raise SystemExit("The history did not trigger summarization.")
    # The update replaces the history: a RemoveMessage, then the new messages.
    return update["messages"][1:]


first = summarize(turn(1) + turn(2) + turn(3))
summarize([*first, *turn(4), *turn(5)])

names = {event.summary_id: f"summary-{index}" for index, event in enumerate(events, 1)}
latest = events[-1]
if latest.summary_id is None:
    raise SystemExit("The second run did not write a summary.")
print(f"{names[latest.summary_id]} is generation {latest.generation}")
links = asyncio.run(middleware.alineage(latest.summary_id))
for link in links:
    source = names.get(str(link.source_id), str(link.source_id))
    target = names.get(str(link.target_id), str(link.target_id))
    print(f"  {source} -> {target} ({link.relation})")
