"""Trace a summary of a summary back to the original messages.

Run: python examples/provenance.py

Every summary is linked to the messages it replaced in an agxai provenance
store (in memory here; see ``postgres_store.py`` for a durable one). After two
rounds of summarization, the lineage of the latest summary reaches back
through the first summary to the original messages.
"""

from __future__ import annotations

import asyncio

from _shared import ScriptedModel

from contextsage import ContextSummarizer, Message, SummarizationEvent

THREAD = "shipments"


def turn(index: int) -> list[Message]:
    """One question about a shipment and its answer."""
    return [
        Message("user", f"Question {index} about shipment SHP-{index:03d}.", id=f"user-{index}"),
        Message("assistant", f"Answer {index}.", id=f"assistant-{index}"),
    ]


async def summarize(summarizer: ContextSummarizer, history: list[Message]) -> SummarizationEvent:
    result = await summarizer.summarize(history, thread_id=THREAD)
    if result is None:
        raise SystemExit("The history did not trigger summarization.")
    history[:] = result.messages
    return result.event


async def main() -> None:
    async with ContextSummarizer(
        ScriptedModel("Summary of the shipment discussion."),
        trigger=("messages", 5),
        keep=("messages", 2),
    ) as summarizer:
        history = turn(1) + turn(2) + turn(3)
        first = await summarize(summarizer, history)
        history += turn(4) + turn(5)
        latest = await summarize(summarizer, history)
        if first.summary_id is None or latest.summary_id is None:
            raise SystemExit("A run did not write a summary.")
        links = await summarizer.lineage(latest.summary_id, thread_id=THREAD)

    names = {first.summary_id: "summary-1", latest.summary_id: "summary-2"}
    print(f"summary-2 is generation {latest.generation}")
    for link in links:
        source = names.get(str(link.source_id), str(link.source_id))
        target = names.get(str(link.target_id), str(link.target_id))
        print(f"  {source} -> {target} ({link.relation})")


if __name__ == "__main__":
    asyncio.run(main())
