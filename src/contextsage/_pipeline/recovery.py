"""Restating lost facts, and the fallback used when the summary model fails."""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    trim_messages,
)

from contextsage._pipeline.lineage import is_summary, summary_message
from contextsage._pipeline.validation import SEPARATOR, canonical, is_stated

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

    from langchain_core.messages import BaseMessage, MessageLikeRepresentation

    from contextsage._pipeline.budget import Window
    from contextsage._pipeline.models import Fact

FACTS_HEADING = "Facts preserved verbatim from the earlier conversation:"
REQUEST_HEADING = "The latest user request was:"
FALLBACK_NOTICE = (
    "Earlier messages were removed because the summary model was unavailable."
)


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
    messages: Sequence[BaseMessage], message: BaseMessage
) -> tuple[list[BaseMessage], int]:
    index = 0
    while index < len(messages) and isinstance(messages[index], SystemMessage):
        index += 1
    return [*messages[:index], message, *messages[index:]], index


def restate(
    messages: Sequence[BaseMessage], facts: Sequence[Fact]
) -> list[BaseMessage]:
    """Add the facts to the summary message, or insert a summary if there is none.

    The facts go into the existing summary rather than a new trailing message,
    so the history keeps a valid turn order and never ends with an assistant
    message the model would continue.

    Returns:
        The messages with the facts restated.
    """
    for index, message in enumerate(messages):
        if is_summary(message) and isinstance(message.content, str):
            updated = message.model_copy(
                update={"content": f"{message.content}\n\n{facts_block(facts)}"}
            )
            return [*messages[:index], updated, *messages[index + 1 :]]
    return _insert_after_system(messages, summary_message(facts_block(facts)))[0]


def _trailing_exchange(messages: Sequence[BaseMessage]) -> int | None:
    """Index of the AI tool call answered by the trailing tool results, if any."""
    index = len(messages)
    while index > 0 and isinstance(messages[index - 1], ToolMessage):
        index -= 1
    if index == len(messages) or index == 0:
        return None
    call = messages[index - 1]
    return index - 1 if isinstance(call, AIMessage) and call.tool_calls else None


def _dropped_request(
    messages: Sequence[BaseMessage], kept: Sequence[BaseMessage]
) -> str | None:
    """Text of the latest user request when the window no longer contains it."""
    for message in reversed(messages):
        if isinstance(message, HumanMessage) and not is_summary(message):
            if any(item is message for item in kept):
                return None
            return message.text
    return None


def fallback(
    messages: Sequence[BaseMessage],
    *,
    keep: Window,
    token_counter: Callable[[Iterable[MessageLikeRepresentation]], int],
    facts: Callable[[Sequence[BaseMessage]], Sequence[Fact]],
) -> tuple[list[BaseMessage], int | None]:
    """Trim the history to the ``keep`` window without a summary model.

    Uses LangChain's `trim_messages` so the window starts on a user or AI turn
    (never on an orphaned tool result) and keeps a leading system message. The
    most recent tool exchange is always kept whole. When the window does not
    start with a user turn, a summary message is added that restates the
    latest user request, if the window lost it, and the facts missing from
    the window.

    Args:
        messages: The history to trim.
        keep: The window to keep, in messages or tokens.
        token_counter: Counts tokens for token-based windows.
        facts: Returns the facts missing from a candidate window.

    Returns:
        The trimmed history, and the index of the summary message added to
        it, if any.
    """
    kind, count = keep
    counter: Callable[[list[BaseMessage]], int] = token_counter
    limit = count
    if kind == "messages":
        counter = len
        limit += 1 if messages and isinstance(messages[0], SystemMessage) else 0
    kept = trim_messages(
        messages,
        max_tokens=limit,
        token_counter=counter,
        strategy="last",
        start_on=("human", "ai"),
        include_system=True,
    )
    exchange = _trailing_exchange(messages)
    if exchange is not None and not any(item is messages[exchange] for item in kept):
        system = [item for item in kept[:1] if isinstance(item, SystemMessage)]
        kept = [*system, *messages[exchange:]]
    missing = facts(kept)
    conversation = [item for item in kept if not isinstance(item, SystemMessage)]
    if not missing and conversation and conversation[0].type == "human":
        return kept, None
    sections = [FALLBACK_NOTICE]
    request = _dropped_request(messages, kept)
    if request:
        sections.append(f"{REQUEST_HEADING}\n{request}")
    if missing:
        sections.append(facts_block(missing))
    return _insert_after_system(kept, summary_message("\n\n".join(sections)))
