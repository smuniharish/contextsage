from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage

from contextsage._pipeline.summarizer import Summarizer
from tests.support.builders import summary_model


def summarizer(**overrides: object) -> Summarizer:
    options: dict[str, Any] = {
        "keep": ("messages", 2),
        "token_counter": None,
        "summary_prompt": None,
        "trim_tokens_to_summarize": 4_000,
    }
    options.update(overrides)
    return Summarizer(summary_model("The summary."), **options)


HISTORY = [
    HumanMessage("one", id="h1"),
    AIMessage("two", id="a1"),
    HumanMessage("three", id="h2"),
    AIMessage("four", id="a2"),
]


def test_summarize_returns_the_summary_and_the_kept_tail():
    result = summarizer().summarize(list(HISTORY), None)
    assert result is not None
    assert not any(isinstance(message, RemoveMessage) for message in result)
    assert result[0].additional_kwargs["lc_source"] == "summarization"
    assert "The summary." in result[0].text
    assert [message.id for message in result[1:]] == ["h2", "a2"]


async def test_asummarize_matches_summarize():
    result = await summarizer().asummarize(list(HISTORY), None)
    assert result is not None
    assert [message.id for message in result[1:]] == ["h2", "a2"]


def test_nothing_to_summarize_returns_none():
    assert summarizer(keep=("messages", 10)).summarize(list(HISTORY), None) is None


def test_custom_token_counter_is_shared():
    def counter(messages: object) -> int:
        return 7

    assert summarizer(token_counter=counter).token_counter is counter


def test_default_token_counter_is_langchains():
    assert summarizer().token_counter(HISTORY) > 0


def test_custom_summary_prompt_is_used():
    model = summary_model("custom summary")
    result = Summarizer(
        model,
        keep=("messages", 2),
        token_counter=None,
        summary_prompt="Summarize briefly:\n{messages}",
        trim_tokens_to_summarize=None,
    ).summarize(list(HISTORY), None)
    assert result is not None
    assert "custom summary" in result[0].text
