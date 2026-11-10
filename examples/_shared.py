"""Helpers shared by the example scripts.

Offline examples use scripted models, so their output is reproducible and is
checked by ``examples/verify_examples.py``. Live examples call an
OpenAI-compatible endpoint configured through the environment or a local
``.env`` file (see ``.env.example``):

- ``CONTEXTSAGE_LLM_API_KEY``: API key; required by live examples.
- ``CONTEXTSAGE_LLM_BASE_URL``: base URL ending in ``/v1``; defaults to OpenAI.
- ``CONTEXTSAGE_LLM_MODEL``: model name; defaults to ``gpt-5-mini``.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, override

from parsefabric import LanguageModel

from contextsage import EventSink, SummarizationEvent

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Sequence

    from langchain_core.language_models import BaseChatModel
    from parsefabric import ChatMessage

    from contextsage import Message

DEFAULT_LIVE_MODEL = "gpt-5-mini"


class ScriptedModel(LanguageModel):
    """A summary model that answers with ``replies`` in turn, repeating the last."""

    def __init__(self, *replies: str) -> None:
        self._replies = list(replies)

    @override
    async def complete(self, messages: Sequence[ChatMessage]) -> str:
        return self._replies.pop(0) if len(self._replies) > 1 else self._replies[0]


class EventCollector(EventSink):
    """Keep every summarization event in memory."""

    def __init__(self) -> None:
        self.events: list[SummarizationEvent] = []

    @override
    async def emit(self, event: SummarizationEvent) -> None:
        self.events.append(event)


@asynccontextmanager
async def chat_model() -> AsyncGenerator[BaseChatModel, None]:
    """Yield the OpenAI-compatible chat model configured in the environment.

    Its HTTP connections are closed on exit.

    Raises:
        SystemExit: If ``CONTEXTSAGE_LLM_API_KEY`` is not set.
    """
    from dotenv import load_dotenv
    from langchain_openai import ChatOpenAI

    load_dotenv()
    api_key = os.environ.get("CONTEXTSAGE_LLM_API_KEY")
    if not api_key:
        raise SystemExit(
            "Set CONTEXTSAGE_LLM_API_KEY (and optionally CONTEXTSAGE_LLM_BASE_URL "
            "and CONTEXTSAGE_LLM_MODEL) to run the live examples; see .env.example."
        )
    model = ChatOpenAI(
        api_key=api_key,
        base_url=os.environ.get("CONTEXTSAGE_LLM_BASE_URL") or None,
        model=os.environ.get("CONTEXTSAGE_LLM_MODEL") or DEFAULT_LIVE_MODEL,
    )
    try:
        yield model
    finally:
        await model.root_async_client.close()


def first_line(text: str, width: int = 88) -> str:
    """The first line of ``text``, shortened to ``width`` characters."""
    line = text.strip().splitlines()[0] if text.strip() else ""
    return line if len(line) <= width else line[: width - 3] + "..."


def show_history(messages: Sequence[Message], width: int = 88) -> None:
    """Print one line per message: its role and the start of its text."""
    for message in messages:
        label = "summary" if message.is_summary else message.role
        text = message.content
        if message.is_summary:
            text = text.partition("\n")[2] or text
        calls = ", ".join(call.name for call in message.tool_calls)
        print(f"  {label:<9} {first_line(text, width) or f'calls {calls}'}")
