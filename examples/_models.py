"""Chat models shared by the examples.

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
from itertools import cycle
from typing import TYPE_CHECKING

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_openai import ChatOpenAI

DEFAULT_LIVE_MODEL = "gpt-5-mini"


def scripted_model(*replies: str) -> BaseChatModel:
    """A chat model that answers with ``replies`` in turn, repeating the last."""
    return GenericFakeChatModel(messages=cycle([AIMessage(text) for text in replies]))


def live_model() -> ChatOpenAI:
    """The OpenAI-compatible chat model configured in the environment.

    Raises:
        SystemExit: If ``CONTEXTSAGE_LLM_API_KEY`` is not set.
    """
    from dotenv import load_dotenv  # noqa: PLC0415
    from langchain_openai import ChatOpenAI  # noqa: PLC0415

    load_dotenv()
    api_key = os.environ.get("CONTEXTSAGE_LLM_API_KEY")
    if not api_key:
        raise SystemExit(
            "Set CONTEXTSAGE_LLM_API_KEY (and optionally CONTEXTSAGE_LLM_BASE_URL "
            "and CONTEXTSAGE_LLM_MODEL) to run the live examples; see .env.example."
        )
    return ChatOpenAI(
        api_key=api_key,
        base_url=os.environ.get("CONTEXTSAGE_LLM_BASE_URL") or None,
        model=os.environ.get("CONTEXTSAGE_LLM_MODEL") or DEFAULT_LIVE_MODEL,
    )


def first_line(text: str, width: int = 88) -> str:
    """The first line of ``text``, shortened to ``width`` characters."""
    line = text.strip().splitlines()[0] if text.strip() else ""
    return line if len(line) <= width else line[: width - 3] + "..."
