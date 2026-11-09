from __future__ import annotations

import asyncio
from typing import Any, override

import pytest
from parsefabric.builtins import CodeDetector
from parsefabric.execution import AsyncExecutionBackend
from parsefabric.models import Evidence, ParsedEvent

from contextsage import (
    ConfigurationError,
    ContextSummarizer,
    Message,
    ParsingOptions,
    TokenizerTokenCounter,
    create_agxai_runtime,
)
from contextsage._pipeline.decomposition import _classify
from contextsage._pipeline.lineage import summary_message
from contextsage._pipeline.summary import TRIM_MARKER, fit, transcript
from contextsage._pipeline.window import cutoff, safe_cutoff
from tests.support.builders import FakeModel, assistant, incident_history, tool, user

COUNTER = TokenizerTokenCounter(tokens_per_message=0)


def test_transcript_marks_names_tool_calls_and_summaries():
    text = transcript(
        [
            assistant("<look>", name="agent", calls=("c1",)),
            tool("done", call="c1"),
            summary_message("earlier"),
        ]
    )
    assert 'name="agent"' in text
    assert "&lt;look&gt;" in text
    assert '<tool_call id="c1" name="tool">{}</tool_call>' in text
    assert 'tool_call_id="c1"' in text
    assert 'summary="true"' in text


async def test_fit_keeps_the_start_and_more_of_the_end():
    text = "".join(f"word{index} " for index in range(400))
    assert await fit(text, None, COUNTER) == text
    assert await fit("short", 100, COUNTER) == "short"
    trimmed = await fit(text, 40, COUNTER)
    assert TRIM_MARKER in trimmed
    head, tail = trimmed.split(TRIM_MARKER)
    assert text.startswith(head)
    assert text.endswith(tail)
    assert len(tail) > len(head)


def test_safe_cutoff_never_separates_tool_results_from_their_call():
    history = [user("a"), assistant(calls=("c1",)), tool("r", call="c1"), user("b")]
    assert safe_cutoff(history, 2) == 1
    assert safe_cutoff(history, 3) == 3
    orphans = [user("a"), tool("r", call="gone"), tool("s", call="gone"), user("b")]
    assert safe_cutoff(orphans, 1) == 3


async def test_token_windows_keep_the_newest_messages_that_fit():
    history = [user("word " * 50), user("word " * 50), user("tiny")]
    assert await cutoff(history, ("tokens", 10_000), COUNTER) == 0
    assert await cutoff(history, ("tokens", 20), COUNTER) == 2
    assert await cutoff(history, ("tokens", 1), COUNTER) == 2
    assert await cutoff([user("tiny"), user("word " * 50)], ("tokens", 5), COUNTER) == 1


def test_overlapping_events_keep_the_first_kind_and_the_highest_severity():
    lines = ["one\n", "two\n"]
    events = [
        ParsedEvent("log", severity="info", evidence=Evidence(line_number=1, end_offset=8)),
        ParsedEvent("traceback", severity="error", evidence=Evidence(line_number=2)),
    ]
    classified = _classify(lines, events)
    assert classified.kinds == ["log", "log"]
    assert classified.severities == ["INFO", "ERROR"]


async def test_cancellation_is_never_swallowed():
    class Cancelled(AsyncExecutionBackend):
        @override
        async def run(self, function: Any, /, *args: object, **kwargs: object) -> Any:
            raise asyncio.CancelledError

    class Detector(CodeDetector):
        @override
        async def prepare(self) -> None:
            raise asyncio.CancelledError

        @override
        async def detect(self, text: str) -> str | None:
            return None

    with pytest.raises(asyncio.CancelledError):
        await ParsingOptions(code_detector=Detector()).prepare()
    engine = ContextSummarizer(
        FakeModel(),
        trigger=("messages", 2),
        parsing=ParsingOptions(code_detector=None, backend=Cancelled()),
    )
    with pytest.raises(asyncio.CancelledError):
        await engine.summarize([user("a"), user("b")])
    await engine.aclose()


async def test_orphans_and_missing_facts_are_both_reported():
    history = [*incident_history(), tool("late", call="gone", id="late")]
    async with ContextSummarizer(
        FakeModel(),
        trigger=("messages", 4),
        keep=("messages", 2),
        parsing=ParsingOptions(code_detector=None, backend=AsyncExecutionBackend()),
    ) as engine:
        result = await engine.summarize(history)
    assert result is not None
    assert result.event.validation_status == "failed_unrecovered"
    assert result.event.recovery_status == "restated_facts"


def test_agxai_runtime_components_are_validated():
    with pytest.raises(ConfigurationError, match=r"store must be an agxai\.ProvenanceStore"):
        create_agxai_runtime(store=object())  # type: ignore[arg-type]
    with pytest.raises(ConfigurationError, match="XAIPlugin") as raised:
        create_agxai_runtime(plugins=[object()])  # type: ignore[list-item]
    assert raised.value.__cause__ is not None


async def test_agxai_runtime_identity_is_configurable():
    runtime = create_agxai_runtime(application_id="app", tenant_id="acme", graph_id="g")
    assert (runtime.application_id, runtime.tenant_id, runtime.graph_id) == ("app", "acme", "g")
    await runtime.close()


def test_summary_messages_are_user_messages_with_lineage():
    message = summary_message("text")
    assert isinstance(message, Message)
    assert message.role == "user"
    assert message.is_summary
