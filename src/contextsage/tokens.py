"""The built-in token counter."""

from __future__ import annotations

import json
from collections import OrderedDict
from typing import TYPE_CHECKING, override

from parsefabric.compression import DEFAULT_TOKENIZER, Tokenizer

from contextsage.contracts import TokenCounter
from contextsage.errors import ConfigurationError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from contextsage.messages import Message

__all__ = ["TokenizerTokenCounter"]


def _positive(value: object, name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ConfigurationError(f"{name} must be an integer >= {minimum}")
    return value


class TokenizerTokenCounter(TokenCounter):
    """Counts messages with a parsefabric `parsefabric.compression.Tokenizer`.

    Each message costs the tokens of its content, author name and tool calls,
    plus a fixed per-message overhead for the chat format. Counts are cached
    per message, so re-counting a growing history only tokenizes new
    messages.

    Args:
        tokenizer: Counts the tokens of a text. Defaults to parsefabric's
            approximate tokenizer (one token per four UTF-8 bytes); pass the
            model's own tokenizer for exact budgets.
        tokens_per_message: Overhead added for every message.
        cache_size: Most messages whose counts are cached; 0 disables the
            cache.

    Raises:
        ConfigurationError: If an argument is invalid.
    """

    def __init__(
        self,
        tokenizer: Tokenizer = DEFAULT_TOKENIZER,
        *,
        tokens_per_message: int = 3,
        cache_size: int = 4096,
    ) -> None:
        if not isinstance(tokenizer, Tokenizer):
            raise ConfigurationError("tokenizer must be a parsefabric Tokenizer")
        self._tokenizer = tokenizer
        self._overhead = _positive(tokens_per_message, "tokens_per_message", minimum=0)
        self._cache_size = _positive(cache_size, "cache_size", minimum=0)
        self._cache: OrderedDict[str, int] = OrderedDict()

    @property
    def tokenizer(self) -> Tokenizer:
        """The tokenizer that counts message text."""
        return self._tokenizer

    @staticmethod
    def _text(message: Message) -> str:
        parts = [message.content]
        if message.name:
            parts.append(message.name)
        parts.extend(
            f"{call.name} {json.dumps(call.arguments, ensure_ascii=False, default=str)}"
            for call in message.tool_calls
        )
        return "\n".join(parts)

    async def _count_one(self, message: Message) -> int:
        text = self._text(message)
        if self._cache_size == 0:
            return await self._tokenizer.count(text) + self._overhead
        cached = self._cache.get(text)
        if cached is not None:
            self._cache.move_to_end(text)
            return cached
        tokens = await self._tokenizer.count(text) + self._overhead
        self._cache[text] = tokens
        if len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return tokens

    @override
    async def count(self, messages: Sequence[Message]) -> int:
        total = 0
        for message in messages:
            total += await self._count_one(message)
        return total
