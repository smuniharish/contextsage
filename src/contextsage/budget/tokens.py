"""Provider/model-aware token counting.

ContextSage needs token counts in two places with different cost profiles:

* **Budget analysis** (whole-conversation accounting) — should match, as
  closely as possible, whatever the wrapped LangGraph
  ``SummarizationMiddleware`` itself uses, so ContextSage's "is summarization
  required" decision is consistent with the mechanics that ultimately run.
* **Per-unit accounting during decomposition** — invoked many times over a
  single large tool output, so it must be cheap and cache-friendly (this is
  why every counter is wrapped in :class:`CachingTokenCounter`).

We never hardcode "characters / 4" as if it were authoritative.
:class:`TiktokenTokenCounter` self-reports that it is an authoritative,
provider-verified count via :attr:`TokenCounter.is_authoritative`.
"""

from __future__ import annotations

import socket
from abc import ABC, abstractmethod
from collections.abc import Iterable
from functools import lru_cache
from typing import TYPE_CHECKING

from contextsage.exceptions import TokenCountingError

if TYPE_CHECKING:
    import tiktoken
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import BaseMessage

_TEXT_CACHE_SIZE = 4096

#: Used when no model is supplied (and no ``encoding_name`` override) —
#: ``cl100k_base`` is the most broadly compatible encoding across
#: OpenAI-compatible and many open-weight tokenizer families, and is used
#: directly with no model-name lookup, so the zero-configuration default
#: never depends on network access to resolve an uncached encoding.
_DEFAULT_ENCODING_NAME = "cl100k_base"

#: Tiktoken downloads uncached encoding files over plain HTTP with no
#: explicit timeout (see ``tiktoken.load.read_file``). To keep ContextSage
#: from hanging indefinitely in network-restricted/offline environments —
#: the same production-reliability concern that ruled out on-demand grammar
#: downloads elsewhere in this package — resolving an *explicit* model name
#: to its encoding is bounded by a short socket timeout, with a safe local
#: fallback to ``cl100k_base`` on failure.
_ENCODING_DOWNLOAD_TIMEOUT_SECONDS = 5.0


class TokenCounter(ABC):
    """Abstract base class for every token counting strategy in ContextSage.

    ``tiktoken`` is the default, always-installed implementation
    (:class:`TiktokenTokenCounter`), but token counting remains pluggable:
    anyone integrating a provider-specific tokenizer
    (Anthropic, Gemini, a local model's own tokenizer, ...) subclasses
    ``TokenCounter`` and passes an instance to
    ``IntelligentSummarizationMiddleware(token_counter=...)`` — no other
    ContextSage code needs to change.
    """

    #: Whether this counter reports an authoritative, provider-verified count
    #: (``True``) or an estimate (``False``).
    is_authoritative: bool

    @abstractmethod
    def count_text(self, text: str) -> int:
        """Return the (approximate or authoritative) token count for raw text."""

    @abstractmethod
    def count_messages(self, messages: Iterable[BaseMessage]) -> int:
        """Return the total token count for a sequence of messages."""


def _resolve_encoding(
    model: str,
    *,
    fallback_encoding_name: str = _DEFAULT_ENCODING_NAME,
    download_timeout_seconds: float = _ENCODING_DOWNLOAD_TIMEOUT_SECONDS,
) -> tiktoken.Encoding:
    """Resolve an explicit ``model`` name to a tiktoken encoding, bounded and fail-safe.

    Tries the model-specific encoding first (bounded by a short socket
    timeout so an uncached encoding never hangs indefinitely on a
    network-restricted host); falls back to ``fallback_encoding_name`` if
    that fails for any reason.
    """
    import tiktoken  # noqa: PLC0415

    previous_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(download_timeout_seconds)
    try:
        try:
            return tiktoken.encoding_for_model(model)
        except Exception:
            return tiktoken.get_encoding(fallback_encoding_name)
    finally:
        socket.setdefaulttimeout(previous_timeout)


class TiktokenTokenCounter(TokenCounter):
    """Authoritative-ish counting using ``tiktoken``.

    ``tiktoken`` is a direct, always-installed dependency, and this is the
    only built-in :class:`TokenCounter` implementation: it is the closest
    thing ContextSage has to a provider-verified count without requiring a
    live API round-trip, for both OpenAI-compatible and most open-weight
    tokenizer families (via ``cl100k_base``/``o200k_base``-family BPE).

    With no arguments, uses ``cl100k_base`` directly — no model-name lookup,
    so the zero-configuration default has no network dependency. Pass
    ``model`` to resolve the encoding for a specific model actually in use
    (e.g. ``"gpt-4o"``, ``"gpt-4.1"``); pass ``encoding_name`` to select an
    encoding directly. ``fallback_encoding_name``/``download_timeout_seconds``
    tune the ``model``-based resolution path itself (see :func:`_resolve_encoding`).
    Remains fully pluggable for non-GPT-family providers: pass any other
    :class:`TokenCounter` subclass via
    ``IntelligentSummarizationMiddleware(token_counter=...)``.
    """

    is_authoritative = True

    def __init__(
        self,
        model: str | None = None,
        encoding_name: str | None = None,
        *,
        fallback_encoding_name: str = _DEFAULT_ENCODING_NAME,
        download_timeout_seconds: float = _ENCODING_DOWNLOAD_TIMEOUT_SECONDS,
    ) -> None:
        import tiktoken  # noqa: PLC0415

        self.model = model
        try:
            if encoding_name is not None:
                self._encoding = tiktoken.get_encoding(encoding_name)
            elif model is not None:
                self._encoding = _resolve_encoding(
                    model,
                    fallback_encoding_name=fallback_encoding_name,
                    download_timeout_seconds=download_timeout_seconds,
                )
            else:
                self._encoding = tiktoken.get_encoding(fallback_encoding_name)
        except Exception as exc:
            raise TokenCountingError(f"tiktoken failed to load an encoding: {exc}") from exc

    def count_text(self, text: str) -> int:
        if not text:
            return 0
        return len(self._encoding.encode(text, disallowed_special=()))

    def count_messages(self, messages: Iterable[BaseMessage]) -> int:
        return sum(self.count_text(_message_text(m)) for m in messages)


class CachingTokenCounter(TokenCounter):
    """Wraps another counter with a bounded LRU cache over raw text."""

    def __init__(self, inner: TokenCounter, maxsize: int = _TEXT_CACHE_SIZE) -> None:
        self._inner = inner
        self.is_authoritative = inner.is_authoritative
        self._cached_count_text = lru_cache(maxsize=maxsize)(self._inner.count_text)

    def count_text(self, text: str) -> int:
        return self._cached_count_text(text)

    def count_messages(self, messages: Iterable[BaseMessage]) -> int:
        return self._inner.count_messages(messages)


def _message_text(message: BaseMessage) -> str:
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


def _extract_model_name(model: BaseChatModel | None) -> str | None:
    """Best-effort extraction of a model name string from a chat model instance."""
    if model is None:
        return None
    for attr in ("model_name", "model"):
        value = getattr(model, attr, None)
        if isinstance(value, str) and value:
            return value
    profile = getattr(model, "profile", None)
    if isinstance(profile, dict):
        value = profile.get("name")
        if isinstance(value, str) and value:
            return value
    return None


def create_default_token_counter(model: BaseChatModel | None = None) -> TokenCounter:
    """Build the default token counter used when the caller does not supply one.

    Resolves the tokenizer to whatever model is actually configured on the
    middleware (e.g. ``"gpt-4.1"``, ``"gpt-4o-mini"``); falls back to the
    universal ``cl100k_base`` encoding directly (no network-dependent
    model-name lookup) when no model name can be determined. The counter
    remains fully pluggable: pass any other :class:`TokenCounter` subclass
    via ``IntelligentSummarizationMiddleware(token_counter=...)``.
    """
    model_name = _extract_model_name(model)
    return CachingTokenCounter(TiktokenTokenCounter(model=model_name))
