"""Messages, models and pipeline builders shared by the tests."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, override

from parsefabric import LanguageModel

from contextsage import BalancedPolicy, ParsingOptions
from contextsage._pipeline.decomposition import Decomposer
from contextsage._pipeline.pipeline import Pipeline
from contextsage._pipeline.signals import DEFAULT_IDENTIFIER_PATTERNS
from contextsage.messages import Message, ToolCall

if TYPE_CHECKING:
    from collections.abc import Sequence

    from parsefabric import ChatMessage

    from contextsage import PreservationPolicy
    from contextsage._pipeline.models import Prepared, Unit

NO_CODE = ParsingOptions(code_detector=None)
"""Parsing options that need no tree-sitter grammar."""


def user(content: str, id: str | None = None) -> Message:
    """A user message."""
    return Message("user", content, id=id)


def assistant(
    content: str = "",
    id: str | None = None,
    *,
    calls: Sequence[str] = (),
    name: str | None = None,
) -> Message:
    """An assistant message, optionally requesting tool calls with the given IDs."""
    return Message(
        "assistant",
        content,
        id=id,
        name=name,
        tool_calls=tuple(ToolCall(call, "tool", {}) for call in calls),
    )


def tool(content: str, call: str = "c1", id: str | None = None) -> Message:
    """A tool result answering ``call``."""
    return Message("tool", content, id=id, tool_call_id=call)


def system(content: str = "You are a careful SRE assistant.", id: str | None = "s0") -> Message:
    """A system message."""
    return Message("system", content, id=id)


class FakeModel(LanguageModel):
    """A summary model that always answers with ``text`` and records each request."""

    def __init__(self, text: str = "Summary of the earlier conversation.") -> None:
        self.text = text
        self.requests: list[Sequence[ChatMessage]] = []

    @override
    async def complete(self, messages: Sequence[ChatMessage]) -> str:
        self.requests.append(messages)
        return self.text


class FailingModel(LanguageModel):
    """A summary model whose every call fails like an unavailable provider."""

    def __init__(self, error: BaseException | None = None) -> None:
        self.error = error or RuntimeError("provider unavailable")

    @override
    async def complete(self, messages: Sequence[ChatMessage]) -> str:
        raise self.error


async def pipeline(policy: PreservationPolicy | None = None) -> Pipeline:
    """A pipeline without code detection, so no grammar is needed."""
    decomposer = Decomposer(
        await NO_CODE.build_parser(),
        NO_CODE.build_engine(),
        DEFAULT_IDENTIFIER_PATTERNS,
        max_concurrency=NO_CODE.max_concurrency,
    )
    return Pipeline(decomposer, policy or BalancedPolicy())


async def prepare(
    messages: Sequence[Message], policy: PreservationPolicy | None = None
) -> Prepared:
    """Analyze and compact ``messages``."""
    return await (await pipeline(policy)).prepare(messages)


async def units(messages: Sequence[Message]) -> tuple[Unit, ...]:
    """Decompose messages with the default configuration."""
    return (await prepare(messages)).analysis.units


def heartbeat_log(lines: int, *, start_minute: int = 0) -> str:
    """Routine, repetitive log lines."""
    return "".join(
        f"2024-08-01T03:{(start_minute + index // 60) % 60:02d}:{index % 60:02d} "
        f"INFO worker-{index % 3} processing queue\n"
        for index in range(lines)
    )


def incident_report(lines: int = 200) -> str:
    """A tool result mixing prose, JSON and a long log ending in an error."""
    payload = json.dumps({"items": [{"sku": "A-1", "qty": 1}] * 30, "status": "ok"})
    return (
        f"Incident INC-9931 report.\n{payload}\n{heartbeat_log(lines)}"
        "2024-08-01T04:00:00 ERROR connection pool exhausted for TX-991\n"
    )


def incident_history(lines: int = 200) -> list[Message]:
    """A conversation with a large tool result and a user correction."""
    return [
        user("Investigate the payments outage for customer 123.", id="h1"),
        assistant(id="a1", calls=("c1",)),
        tool(incident_report(lines), call="c1", id="t1"),
        assistant("Found INC-9931.", id="a2"),
        user("No, use customer 456 instead of customer 123.", id="h2"),
        assistant("Switching to customer 456.", id="a3"),
        user("Any update?", id="h3"),
    ]


def with_system(messages: Sequence[Message]) -> list[Message]:
    """Prefix ``messages`` with a system prompt."""
    return [system(), *messages]
