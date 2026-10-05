"""Summary message identity, summary-of-summary lineage and carried facts.

Lineage is stored on the summary message itself, so it survives checkpoints
and needs no state in the middleware.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING
from uuid import uuid4

from langchain_core.messages import BaseMessage, HumanMessage

from contextsage._pipeline.models import Fact
from contextsage._pipeline.validation import canonical, is_stated

if TYPE_CHECKING:
    from collections.abc import Sequence

SUMMARY_SOURCE = "summarization"
"""The ``lc_source`` LangChain gives the summary message it creates."""

METADATA_KEY = "contextsage"
"""Key of ContextSage's lineage record in a summary's ``additional_kwargs``."""


def new_summary_id() -> str:
    """Return a fresh, unique summary message ID."""
    return f"contextsage-summary-{uuid4().hex}"


def is_summary(message: BaseMessage) -> bool:
    """Whether ``message`` is a summary created by LangChain or ContextSage."""
    return (
        isinstance(message, HumanMessage)
        and message.additional_kwargs.get("lc_source") == SUMMARY_SOURCE
    )


def generation_of(message: BaseMessage) -> int:
    """Return a summary's generation; summaries without a lineage record count as 1."""
    record = message.additional_kwargs.get(METADATA_KEY)
    value = record.get("generation") if isinstance(record, Mapping) else None
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return 1


def summary_message(text: str) -> HumanMessage:
    """Create a summary message in the same form LangChain uses."""
    return HumanMessage(content=text, additional_kwargs={"lc_source": SUMMARY_SOURCE})


def stamp(
    message: BaseMessage,
    *,
    summary_id: str,
    generation: int,
    source_summary_ids: tuple[str, ...],
    facts: Sequence[Fact],
) -> BaseMessage:
    """Return ``message`` with its ID and lineage record set.

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
    additional_kwargs = {
        **message.additional_kwargs,
        "lc_source": SUMMARY_SOURCE,
        METADATA_KEY: {
            "summary_id": summary_id,
            "generation": generation,
            "source_summary_ids": list(source_summary_ids),
            "facts": [
                {"statement": fact.statement, "required": list(fact.required)}
                for fact in facts
            ],
        },
    }
    return message.model_copy(
        update={"id": summary_id, "additional_kwargs": additional_kwargs}
    )


def _recorded_fact(entry: object) -> Fact | None:
    """Read one fact of a lineage record; ``None`` if it is malformed."""
    if not isinstance(entry, Mapping):
        return None
    statement = entry.get("statement")
    required = entry.get("required")
    if (
        not isinstance(statement, str)
        or not isinstance(required, (list, tuple))
        or not required
        or not all(isinstance(item, str) and item.strip() for item in required)
    ):
        return None
    fact = Fact(statement, tuple(required))
    # Restating the statement must satisfy the fact, as it does for every
    # fact ContextSage records.
    return fact if is_stated(fact, canonical(statement)) else None


def carried_facts(messages: Sequence[BaseMessage]) -> tuple[Fact, ...]:
    """Return the facts recorded by the summaries in ``messages``, in order.

    Malformed records, for example from an edited checkpoint, are skipped.
    """
    facts: list[Fact] = []
    for message in messages:
        record = message.additional_kwargs.get(METADATA_KEY)
        entries = record.get("facts") if isinstance(record, Mapping) else None
        if not is_summary(message) or not isinstance(entries, (list, tuple)):
            continue
        facts.extend(
            fact for entry in entries if (fact := _recorded_fact(entry)) is not None
        )
    return tuple(facts)


def replaced_summaries(
    history: list[BaseMessage], kept_ids: set[str]
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
        message
        for message in history
        if is_summary(message) and message.id not in kept_ids
    ]
    generation = max((generation_of(message) for message in replaced), default=0) + 1
    return generation, tuple(message.id for message in replaced if message.id)
