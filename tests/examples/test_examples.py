"""Execute the offline and model-backed examples in the same way users run them."""

from __future__ import annotations

import importlib
import runpy
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from langchain_core.messages import AIMessage

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from _langchain_shared import ScriptedChatModel

pytestmark = pytest.mark.examples
EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _tool_call(name: str, arguments: dict[str, object], call_id: str) -> AIMessage:
    return AIMessage(
        "",
        tool_calls=[{"id": call_id, "name": name, "args": arguments, "type": "tool_call"}],
    )


SCRIPTED: dict[str, tuple[list[AIMessage], list[str]]] = {
    "live_agent": (
        [
            _tool_call("incident_report", {"incident_id": "INC-9931"}, "call-1"),
            AIMessage("The report shows a saturated connection pool."),
            AIMessage("The connection pool is exhausted while settling TX-991."),
        ],
        ["Answer:", "summarization:"],
    ),
    "deep_agent": (
        [
            _tool_call("deployment_log", {"service": "checkout"}, "call-1"),
            AIMessage("Deployment DEP-7310 failed its readiness probe."),
            AIMessage("The readiness probe timed out during deployment DEP-7310."),
        ],
        ["Answer:", "summarization:"],
    ),
    "swarm": (
        [
            _tool_call("transfer_to_investigator", {}, "handoff-1"),
            _tool_call("billing_records", {"account": "ACC-42"}, "call-2"),
            AIMessage("Billing records show invoice INV-8812 was charged twice."),
            AIMessage("Invoice INV-8812 was charged twice for account ACC-42."),
        ],
        ["Answer:", "summarization"],
    ),
}


def test_offline_examples_match_recorded_output() -> None:
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and repository-owned script path
        [sys.executable, str(EXAMPLES / "verify_examples.py")],
        capture_output=True,
        check=False,
        cwd=EXAMPLES.parent,
        encoding="utf-8",
        timeout=120,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.parametrize("name", SCRIPTED, ids=list(SCRIPTED))
def test_live_examples_run_with_scripted_models(
    name: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if name == "deep_agent":
        pytest.importorskip("deepagents")
    if name == "swarm":
        pytest.importorskip("langgraph_swarm")
    replies, expected = SCRIPTED[name]
    monkeypatch.syspath_prepend(str(EXAMPLES))
    shared = importlib.import_module("_shared")
    langchain_shared = importlib.import_module("_langchain_shared")
    model = langchain_shared.scripted_chat_model(*replies)

    @asynccontextmanager
    async def chat_model() -> AsyncGenerator[ScriptedChatModel, None]:
        yield model

    monkeypatch.setattr(shared, "chat_model", chat_model)
    monkeypatch.delenv("CONTEXTSAGE_LLM_API_KEY", raising=False)
    runpy.run_path(str(EXAMPLES / f"{name}.py"), run_name="__main__")
    output = capsys.readouterr().out
    for text in expected:
        assert text in output
