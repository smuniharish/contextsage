"""Message reconstruction.

Rebuilds valid LangGraph/LangChain message objects from transformed
context units. To keep reconstruction safe, a message's
content is only rebuilt when at least one of its constituent units was
actually transformed; otherwise the original message is passed through
completely untouched, avoiding any risk of subtly corrupting content that
did not need to change.
"""

from __future__ import annotations

from itertools import groupby
from typing import TYPE_CHECKING

from contextsage.core.models import ContextUnit

if TYPE_CHECKING:
    from collections.abc import Sequence

    from langchain_core.messages import BaseMessage


def apply_transformed_units(
    messages: Sequence[BaseMessage], units: Sequence[ContextUnit]
) -> list[BaseMessage]:
    """Rebuild message content from (possibly transformed) context units.

    Messages whose units were never touched by the transformation engine
    are returned as-is (same object), guaranteeing byte-for-byte identical
    content for anything the planner did not target.
    """
    by_message_index: dict[int, list[ContextUnit]] = {}
    for unit in units:
        by_message_index.setdefault(unit.message_index, []).append(unit)

    rebuilt: list[BaseMessage] = []
    for index, message in enumerate(messages):
        message_units = by_message_index.get(index)
        if not message_units:
            rebuilt.append(message)
            continue

        any_transformed = any(u.metadata.get("contextsage_transformed") for u in message_units)
        if not any_transformed:
            rebuilt.append(message)
            continue

        ordered = sorted(message_units, key=lambda u: u.position)
        new_content = "\n".join(u.content for u in ordered)
        rebuilt.append(message.model_copy(update={"content": new_content}))
    return rebuilt


def content_signal_counts(units: Sequence[ContextUnit]) -> dict[str, int]:
    """Aggregate unit counts per structural kind, for observability."""
    counts: dict[str, int] = {}
    ordered = sorted(units, key=lambda u: str(u.signals.kind))
    for kind, group in groupby(ordered, key=lambda u: str(u.signals.kind)):
        counts[kind] = sum(1 for _ in group)
    return counts
