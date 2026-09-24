"""Shared helper: build the real chat model used by every example.

All example scripts call ``build_demo_model()`` from this module instead of
each defining their own scripted fake model. This means running an example
makes a real network call and shows ContextSage's actual behavior against a
live LLM response, not a hand-written canned string.

Configure the model via environment variables (loaded from a local ``.env``
file — copy ``.env.example`` to ``.env`` and fill in your key; ``.env`` is
already gitignored so the key never gets committed):

    EXPLABS_API_KEY   (required) API key for the OpenAI-compatible endpoint.
    EXPLABS_BASE_URL  (optional) defaults to https://api.experientiallabs.ai/v1
    EXPLABS_MODEL     (optional) defaults to gpt-5.6-luna
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import BaseMessage, ToolMessage
from langchain_openai import ChatOpenAI
from pydantic import Field

load_dotenv()

_DEFAULT_BASE_URL = "https://api.experientiallabs.ai/v1"
_DEFAULT_MODEL = "gpt-5.6-luna"


def _resolved_kwargs(temperature: float) -> dict[str, Any]:
    api_key = os.environ.get("EXPLABS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "EXPLABS_API_KEY is not set. Copy .env.example to .env in the "
            "repository root and fill in your API key before running the "
            "examples."
        )
    return {
        "base_url": os.environ.get("EXPLABS_BASE_URL", _DEFAULT_BASE_URL),
        "api_key": api_key,
        "model": os.environ.get("EXPLABS_MODEL", _DEFAULT_MODEL),
        "temperature": temperature,
    }


def _without_non_tool_names(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Strip ``name`` from any non-``ToolMessage`` before sending it out.

    ``langchain.agents.create_agent(..., name="Alice")`` tags each agent's
    own output messages with its agent name (used by ``examples/swarm.py``
    for multi-agent transcripts). The real endpoint these examples call
    rejects ``name`` on non-tool messages even though the field is optional
    per the OpenAI API spec, so it is stripped here rather than disabling
    that LangChain-level feature.
    """
    return [
        m.model_copy(update={"name": None})
        if not isinstance(m, ToolMessage) and getattr(m, "name", None) is not None
        else m
        for m in messages
    ]


class _CompatibleChatOpenAI(ChatOpenAI):
    """Real ``ChatOpenAI`` that sanitizes requests for this strict endpoint."""

    def _generate(self, messages: list[BaseMessage], *args: Any, **kwargs: Any) -> Any:
        return super()._generate(_without_non_tool_names(messages), *args, **kwargs)

    async def _agenerate(self, messages: list[BaseMessage], *args: Any, **kwargs: Any) -> Any:
        return await super()._agenerate(_without_non_tool_names(messages), *args, **kwargs)


def build_demo_model(temperature: float = 0.0) -> _CompatibleChatOpenAI:
    """Build the real, network-backed chat model shared by every example.

    Raises a clear error immediately if no API key is configured, rather
    than silently falling back to a fake model.
    """
    return _CompatibleChatOpenAI(**_resolved_kwargs(temperature))


class RecordingChatOpenAI(_CompatibleChatOpenAI):
    """A real ``ChatOpenAI`` that also records every request's messages.

    Used only by the parameter-verification example so it can prove, from
    the *actual* network call, that constructor parameters such as
    ``summary_prompt``/``trim_tokens_to_summarize`` were genuinely forwarded
    to the summarization call — not just accepted and silently dropped.
    """

    call_log: list[list[BaseMessage]] = Field(default_factory=list, exclude=True)

    def _generate(self, messages: list[BaseMessage], *args: Any, **kwargs: Any) -> Any:
        self.call_log.append(list(messages))
        return super()._generate(messages, *args, **kwargs)

    async def _agenerate(self, messages: list[BaseMessage], *args: Any, **kwargs: Any) -> Any:
        self.call_log.append(list(messages))
        return await super()._agenerate(messages, *args, **kwargs)


def build_recording_model(temperature: float = 0.0) -> RecordingChatOpenAI:
    """Build a real, network-backed chat model that also records requests."""
    return RecordingChatOpenAI(**_resolved_kwargs(temperature))
