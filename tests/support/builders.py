"""Chat models, histories and pipeline builders shared by the tests."""

from __future__ import annotations

import asyncio
import json
from itertools import cycle
from typing import TYPE_CHECKING, Any, cast

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from contextsage._pipeline.parsing import build_parser
from contextsage._pipeline.pipeline import Pipeline
from contextsage._pipeline.signals import DEFAULT_IDENTIFIER_PATTERNS

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from langchain.agents.middleware.types import AgentState
    from langchain_core.messages import BaseMessage

    from contextsage._pipeline.models import Prepared, Unit
    from contextsage._pipeline.preservation import Policy


def state(messages: Iterable[BaseMessage]) -> AgentState[Any]:
    """Agent state holding ``messages``."""
    return cast("AgentState[Any]", {"messages": list(messages)})


def summary_model(text: str = "Summary of the earlier conversation.") -> BaseChatModel:
    """A chat model that always answers with ``text``."""
    return GenericFakeChatModel(messages=cycle([AIMessage(text)]))


class FailingModel(BaseChatModel):
    """A chat model whose every call fails like an unavailable provider."""

    error: str = "provider unavailable"

    @property
    def _llm_type(self) -> str:
        return "failing"

    def _generate(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(self.error)

    async def _agenerate(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(self.error)


def profiled_model(max_input_tokens: int) -> BaseChatModel:
    """A fake model whose LangChain profile reports ``max_input_tokens``."""
    return GenericFakeChatModel(
        messages=cycle([AIMessage("Profiled summary.")]),
        profile={"max_input_tokens": max_input_tokens},
    )


def pipeline(policy: Policy = "balanced") -> Pipeline:
    """A pipeline without code detection, so no grammar is needed."""
    return Pipeline(
        parser=build_parser(routes=(), fence_routes=None, code_languages=()),
        identifier_patterns=DEFAULT_IDENTIFIER_PATTERNS,
        policy=policy,
    )


def prepare(messages: Sequence[BaseMessage], policy: Policy = "balanced") -> Prepared:
    """Run the pipeline synchronously."""
    return asyncio.run(pipeline(policy).prepare(messages))


def units(messages: Sequence[BaseMessage]) -> tuple[Unit, ...]:
    """Decompose messages with the default configuration."""
    return prepare(messages).analysis.units


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


def incident_history(lines: int = 200) -> list[BaseMessage]:
    """A conversation with a large tool result and a user correction."""
    return [
        HumanMessage("Investigate the payments outage for customer 123.", id="h1"),
        AIMessage("", id="a1", tool_calls=[{"id": "c1", "name": "report", "args": {}}]),
        ToolMessage(incident_report(lines), tool_call_id="c1", id="t1"),
        AIMessage("Found INC-9931.", id="a2"),
        HumanMessage("No, use customer 456 instead of customer 123.", id="h2"),
        AIMessage("Switching to customer 456.", id="a3"),
        HumanMessage("Any update?", id="h3"),
    ]


def with_system(messages: Sequence[BaseMessage]) -> list[BaseMessage]:
    """Prefix ``messages`` with a system prompt."""
    return [SystemMessage("You are a careful SRE assistant.", id="s0"), *messages]
