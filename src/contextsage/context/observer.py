"""Context observation: a cheap first pass over the raw message list.

This runs before budget analysis and before the (relatively) more expensive
decomposition step, and only computes coarse per-message statistics. Its
purpose is to let the middleware quickly answer "is there any possibility of
context pressure at all?" without doing structural analysis on every message
on every single model turn (for performance).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from contextsage.budget.tokens import TokenCounter

if TYPE_CHECKING:
    from collections.abc import Sequence

    from langchain_core.messages import BaseMessage


@dataclass(slots=True)
class ObservedMessage:
    """Coarse, cheap-to-compute statistics for a single message."""

    index: int
    message_id: str | None
    role: str
    token_count: int
    char_count: int


@dataclass(slots=True)
class ObservedContext:
    """Result of a single cheap observation pass over the message list."""

    messages: tuple[ObservedMessage, ...]
    total_tokens: int
    total_messages: int

    @property
    def largest_message(self) -> ObservedMessage | None:
        if not self.messages:
            return None
        return max(self.messages, key=lambda m: m.token_count)


class ContextObserver:
    """Performs the cheap first-pass observation of a message list."""

    def __init__(self, token_counter: TokenCounter) -> None:
        self._token_counter = token_counter

    def observe(self, messages: Sequence[BaseMessage]) -> ObservedContext:
        observed: list[ObservedMessage] = []
        total_tokens = 0
        for index, message in enumerate(messages):
            text = _content_as_text(message)
            token_count = self._token_counter.count_text(text)
            total_tokens += token_count
            observed.append(
                ObservedMessage(
                    index=index,
                    message_id=getattr(message, "id", None),
                    role=getattr(message, "type", "unknown"),
                    token_count=token_count,
                    char_count=len(text),
                )
            )
        return ObservedContext(
            messages=tuple(observed),
            total_tokens=total_tokens,
            total_messages=len(observed),
        )


def _content_as_text(message: BaseMessage) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(str(block.get("text", block)))
        return "\n".join(parts)
    return str(content)
