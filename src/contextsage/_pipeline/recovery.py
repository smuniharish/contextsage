"""Restating lost facts, and the fallback used when the summary model fails."""

from __future__ import annotations

from typing import TYPE_CHECKING

from contextsage._pipeline.lineage import summary_message
from contextsage._pipeline.validation import SEPARATOR, canonical, is_stated
from contextsage._pipeline.window import trailing_window

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from contextsage._pipeline.budget import Window
    from contextsage.contracts import TokenCounter
    from contextsage.messages import Fact, Message, Role

FACTS_HEADING = "Facts preserved verbatim from the earlier conversation:"
REQUEST_HEADING = "The latest user request was:"
FALLBACK_NOTICE = "Earlier messages were removed because the summary model was unavailable."
_TURNS: frozenset[Role] = frozenset({"user", "assistant"})


def _concise(facts: Sequence[Fact]) -> list[Fact]:
    """Drop facts that the statement of another restated fact already states.

    Longer statements are considered first, so a correction sentence absorbs
    the identifier it mentions rather than the other way round.
    """
    stated = ""
    kept: set[Fact] = set()
    for fact in sorted(facts, key=lambda fact: len(fact.statement), reverse=True):
        if not is_stated(fact, stated):
            kept.add(fact)
            stated = f"{stated}{SEPARATOR}{canonical(fact.statement)}"
    return [fact for fact in facts if fact in kept]


def facts_block(facts: Sequence[Fact]) -> str:
    """Render facts as a bulleted section, stating each fact once."""
    bullets = "\n".join(f"- {fact.statement}" for fact in _concise(facts))
    return f"{FACTS_HEADING}\n{bullets}"


def _insert_after_system(
    messages: Sequence[Message], message: Message
) -> tuple[list[Message], int]:
    index = 0
    while index < len(messages) and messages[index].role == "system":
        index += 1
    return [*messages[:index], message, *messages[index:]], index


def restate(messages: Sequence[Message], facts: Sequence[Fact]) -> list[Message]:
    """Add the facts to the summary message, or insert a summary if there is none.

    The facts go into the existing summary rather than a new trailing message,
    so the history keeps a valid turn order and never ends with an assistant
    message the model would continue.

    Returns:
        The messages with the facts restated.
    """
    for index, message in enumerate(messages):
        if message.is_summary and message.rewritable:
            updated = message.with_content(f"{message.content}\n\n{facts_block(facts)}")
            return [*messages[:index], updated, *messages[index + 1 :]]
    return _insert_after_system(messages, summary_message(facts_block(facts)))[0]


def _trailing_exchange(messages: Sequence[Message]) -> int | None:
    """Index of the assistant tool call answered by the trailing tool results, if any."""
    index = len(messages)
    while index > 0 and messages[index - 1].role == "tool":
        index -= 1
    if index == len(messages) or index == 0:
        return None
    call = messages[index - 1]
    return index - 1 if call.role == "assistant" and call.tool_calls else None


def _dropped_request(messages: Sequence[Message], kept: Sequence[Message]) -> str | None:
    """Text of the latest user request when the window no longer contains it."""
    for message in reversed(messages):
        if message.role == "user" and not message.is_summary:
            if any(item is message for item in kept):
                return None
            return message.content
    return None


async def fallback(
    messages: Sequence[Message],
    *,
    keep: Window,
    counter: TokenCounter,
    facts: Callable[[Sequence[Message]], Sequence[Fact]],
) -> tuple[list[Message], int | None]:
    """Trim the history to the ``keep`` window without a summary model.

    The window starts on a user or assistant turn (never on an orphaned tool
    result) and keeps a leading system message. The most recent tool exchange
    is always kept whole. When the window does not start with a user turn, a
    summary message is added that restates the latest user request, if the
    window lost it, and the facts missing from the window.

    Args:
        messages: The history to trim.
        keep: The window to keep, in messages or tokens.
        counter: Counts tokens for token-based windows.
        facts: Returns the facts missing from a candidate window.

    Returns:
        The trimmed history, and the index of the summary message added to
        it, if any.
    """
    kept = await trailing_window(messages, keep, counter, start_on=_TURNS)
    exchange = _trailing_exchange(messages)
    if exchange is not None and not any(item is messages[exchange] for item in kept):
        system = [item for item in kept[:1] if item.role == "system"]
        kept = [*system, *messages[exchange:]]
    missing = facts(kept)
    conversation = [item for item in kept if item.role != "system"]
    if not missing and conversation and conversation[0].role == "user":
        return kept, None
    sections = [FALLBACK_NOTICE]
    request = _dropped_request(messages, kept)
    if request:
        sections.append(f"{REQUEST_HEADING}\n{request}")
    if missing:
        sections.append(facts_block(missing))
    return _insert_after_system(kept, summary_message("\n\n".join(sections)))
