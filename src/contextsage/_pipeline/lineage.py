"""Summary message identity, summary-of-summary lineage and carried facts.

Lineage is stored on the summary message itself (`contextsage.SummaryLineage`),
so it survives checkpoints and needs no state in the engine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from contextsage._pipeline.validation import canonical, is_stated
from contextsage.messages import Message, SummaryLineage

if TYPE_CHECKING:
    from collections.abc import Sequence

    from contextsage.messages import Fact


def new_summary_id() -> str:
    """Return a fresh, unique summary message ID."""
    return f"contextsage-summary-{uuid4().hex}"


def summary_message(text: str) -> Message:
    """Create an unstamped summary message; `stamp` gives it its identity."""
    return Message("user", text, lineage=SummaryLineage(summary_id=""))


def stamp(
    message: Message,
    *,
    summary_id: str,
    generation: int,
    source_summary_ids: tuple[str, ...],
    facts: Sequence[Fact],
) -> Message:
    """Return ``message`` with its ID and lineage set.

    Args:
        message: The summary message.
        summary_id: The ID to give it.
        generation: Its generation.
        source_summary_ids: IDs of the earlier summaries it replaced.
        facts: The facts the rewritten history had to keep. Later
            summarizations require them again, after the messages they came
            from are gone.

    Returns:
        A copy of the message.
    """
    return Message(
        "user",
        message.content,
        id=summary_id,
        name=message.name,
        lineage=SummaryLineage(
            summary_id=summary_id,
            generation=generation,
            source_summary_ids=source_summary_ids,
            facts=tuple(facts),
        ),
    )


def carried_facts(messages: Sequence[Message]) -> tuple[Fact, ...]:
    """Return the facts recorded by the summaries in ``messages``, in order.

    A recorded fact whose own statement does not satisfy it, for example from
    an edited checkpoint, is skipped.
    """
    return tuple(
        fact
        for message in messages
        if message.lineage is not None
        for fact in message.lineage.facts
        if is_stated(fact, canonical(fact.statement))
    )


def replaced_summaries(
    history: Sequence[Message], kept_ids: set[str]
) -> tuple[int, tuple[str, ...]]:
    """Return the next generation and the summaries being replaced.

    Args:
        history: The history before rewriting.
        kept_ids: IDs of messages that survive the rewrite.

    Returns:
        The generation of a summary replacing the removed summaries, and their
        IDs.
    """
    replaced = [
        message.lineage
        for message in history
        if message.lineage is not None and message.id not in kept_ids
    ]
    generation = max((lineage.generation for lineage in replaced), default=0) + 1
    return generation, tuple(lineage.summary_id for lineage in replaced if lineage.summary_id)
