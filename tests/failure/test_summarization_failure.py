"""Failure-path tests: summarization must never corrupt state."""

from __future__ import annotations

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage

from contextiq import IntelligentSummarizationMiddleware


class _RaisingModel(BaseChatModel):
    """A real ``BaseChatModel`` whose generation always raises (simulated provider timeout)."""

    @property
    def _llm_type(self) -> str:
        return "raising-fake-chat-model"

    def _generate(self, *_args, **_kwargs):
        raise RuntimeError("simulated provider timeout")

    async def _agenerate(self, *_args, **_kwargs):
        raise RuntimeError("simulated provider timeout")


def _long_conversation() -> list:
    return [
        HumanMessage(content="Use customer 456, not 123.", id="h1"),
        AIMessage(content="ok", id="a1"),
    ] * 20


@pytest.mark.integration
def test_summarization_failure_falls_back_to_deterministic_trim():
    middleware = IntelligentSummarizationMiddleware(
        model=_RaisingModel(),
        trigger=("tokens", 10),
        keep=("messages", 2),
    )
    result = middleware.before_model({"messages": _long_conversation()}, None)
    assert result is not None
    assert isinstance(result["messages"][0], RemoveMessage)
    combined_text = "\n".join(str(getattr(m, "content", "")) for m in result["messages"])
    # The literal must-preserve fact from the user correction must have survived
    # the fallback even though the LLM call itself failed entirely.
    assert "456" in combined_text


@pytest.mark.integration
async def test_summarization_failure_falls_back_async():
    middleware = IntelligentSummarizationMiddleware(
        model=_RaisingModel(),
        trigger=("tokens", 10),
        keep=("messages", 2),
    )
    result = await middleware.abefore_model({"messages": _long_conversation()}, None)
    assert result is not None
    assert isinstance(result["messages"][0], RemoveMessage)
