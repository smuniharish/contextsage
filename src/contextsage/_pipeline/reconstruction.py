"""Rebuild messages from their units after compaction."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from langchain_core.messages import BaseMessage

    from contextsage._pipeline.models import Unit


def rebuild(
    messages: Sequence[BaseMessage],
    units: Sequence[Unit],
    replacements: Mapping[str, str],
) -> list[BaseMessage]:
    """Return the messages with compacted units substituted.

    Units tile their message, so joining every unit's text (replaced where a
    replacement exists) reproduces the message exactly except for the
    replaced spans. Messages without replacements are returned as the same
    objects.

    Args:
        messages: The original messages.
        units: Units of those messages, in order.
        replacements: New text by unit ID.

    Returns:
        A new list of messages.
    """
    if not replacements:
        return list(messages)
    by_message: dict[int, list[Unit]] = {}
    for unit in units:
        by_message.setdefault(unit.message_index, []).append(unit)
    rebuilt = list(messages)
    for index, message_units in by_message.items():
        if any(unit.unit_id in replacements for unit in message_units):
            text = "".join(
                replacements.get(unit.unit_id, unit.text) for unit in message_units
            )
            rebuilt[index] = messages[index].model_copy(update={"content": text})
    return rebuilt
