"""Checks that a rewritten history kept what it had to keep."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage, ToolMessage

from contextsage._pipeline.importance import normalize_apostrophes

if TYPE_CHECKING:
    from collections.abc import Sequence

    from langchain_core.messages import BaseMessage

    from contextsage._pipeline.models import Fact

SEPARATOR = "\0"
"""Joins canonical message texts so that no match spans two messages."""


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Facts that went missing and tool results whose call went missing."""

    missing: tuple[Fact, ...]
    orphaned_tool_results: tuple[str, ...]


def canonical(text: str) -> str:
    """Fold case, normalize apostrophes and collapse whitespace.

    Facts are stated in this form, so matching compares like with like.
    """
    return " ".join(normalize_apostrophes(text).split()).casefold()


def _is_word(character: str) -> bool:
    return character.isalnum() or character == "_"


def contains(text: str, needle: str) -> bool:
    """Whether ``needle`` occurs in ``text`` as a whole token sequence.

    A match must not be glued to surrounding word characters, so ``ORD-1`` is
    not found in ``ORD-12``. Both arguments must already be canonical.
    """
    if not needle:
        return True
    start = 0
    while (index := text.find(needle, start)) >= 0:
        end = index + len(needle)
        glued_before = index > 0 and _is_word(needle[0]) and _is_word(text[index - 1])
        glued_after = end < len(text) and _is_word(needle[-1]) and _is_word(text[end])
        if not glued_before and not glued_after:
            return True
        start = index + 1
    return False


def is_stated(fact: Fact, text: str) -> bool:
    """Whether canonical ``text`` contains everything ``fact`` requires."""
    return all(contains(text, canonical(required)) for required in fact.required)


def orphaned_tool_results(messages: Sequence[BaseMessage]) -> tuple[str, ...]:
    """Return the tool-call IDs of tool results with no preceding tool call."""
    requested: set[str] = set()
    orphans: list[str] = []
    for message in messages:
        if isinstance(message, AIMessage):
            requested.update(call["id"] for call in message.tool_calls if call["id"])
        elif isinstance(message, ToolMessage) and message.tool_call_id not in requested:
            orphans.append(message.tool_call_id)
    return tuple(orphans)


def validate(
    messages: Sequence[BaseMessage], facts: Sequence[Fact]
) -> ValidationResult:
    """Check that every fact appears and every tool result keeps its call.

    Facts are matched within each message, ignoring case, whitespace and
    apostrophe style, and only as whole tokens.

    Args:
        messages: The rewritten history.
        facts: The facts it must contain.

    Returns:
        What is missing, if anything.
    """
    text = SEPARATOR.join(canonical(message.text) for message in messages)
    missing = tuple(fact for fact in facts if not is_stated(fact, text))
    return ValidationResult(missing, orphaned_tool_results(messages))
