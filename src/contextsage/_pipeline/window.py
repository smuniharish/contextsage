"""Where to cut a history: the kept window and tool-call-safe boundaries."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from contextsage._pipeline.budget import Window
    from contextsage.contracts import TokenCounter
    from contextsage.messages import Message, Role


async def fitting_suffix(messages: Sequence[Message], budget: int, counter: TokenCounter) -> int:
    """Return the earliest index whose suffix fits in ``budget`` tokens.

    Token counts grow as the suffix grows, so a binary search needs
    ``log2(len(messages))`` counts.
    """
    left, right = 0, len(messages)
    while left < right:
        middle = (left + right) // 2
        if await counter.count(messages[middle:]) <= budget:
            right = middle
        else:
            left = middle + 1
    return left


def safe_cutoff(messages: Sequence[Message], index: int) -> int:
    """Move ``index`` so that no tool result is separated from its tool call.

    When ``index`` lands on tool results, the cut moves back to the assistant
    message that requested them, keeping the exchange whole. If no such
    message exists, it moves forward past the tool results instead.
    """
    if index >= len(messages) or messages[index].role != "tool":
        return index
    end = index
    answered: set[str] = set()
    while end < len(messages) and messages[end].role == "tool":
        answered.add(messages[end].tool_call_id or "")
        end += 1
    for position in range(index - 1, -1, -1):
        message = messages[position]
        if message.role == "assistant" and answered & {call.id for call in message.tool_calls}:
            return position
    return end


async def cutoff(messages: Sequence[Message], keep: Window, counter: TokenCounter) -> int:
    """Return how many leading messages to summarize so that ``keep`` stays verbatim.

    Returns:
        A tool-call-safe index; 0 when nothing is old enough to summarize.
    """
    kind, count = keep
    if kind == "messages":
        if len(messages) <= count:
            return 0
        return safe_cutoff(messages, len(messages) - count)
    if await counter.count(messages) <= count:
        return 0
    index = await fitting_suffix(messages, count, counter)
    if index >= len(messages):
        index = len(messages) - 1
    return safe_cutoff(messages, index)


async def trailing_window(
    messages: Sequence[Message],
    keep: Window,
    counter: TokenCounter,
    *,
    start_on: frozenset[Role],
) -> list[Message]:
    """Return a leading system message plus the most recent ``keep`` window.

    The window starts on the first message whose role is in ``start_on``, so
    it never opens with an orphaned tool result.
    """
    system = list(messages[:1]) if messages and messages[0].role == "system" else []
    rest = messages[len(system) :]
    kind, count = keep
    if kind == "messages":
        start = max(len(rest) - count, 0)
    else:
        budget = count - (await counter.count(system) if system else 0)
        start = await fitting_suffix(rest, budget, counter)
    while start < len(rest) and rest[start].role not in start_on:
        start += 1
    return [*system, *rest[start:]]
