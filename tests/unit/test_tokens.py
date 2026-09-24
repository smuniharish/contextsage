"""Unit tests for token counting."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from contextiq.budget.tokens import (
    CachingTokenCounter,
    TiktokenTokenCounter,
    create_default_token_counter,
)


def test_tiktoken_counter_returns_positive_for_nonempty_text():
    counter = TiktokenTokenCounter(encoding_name="cl100k_base")
    assert counter.count_text("hello world") > 0
    assert counter.count_text("") == 0
    assert counter.is_authoritative is True


def test_tiktoken_counter_scales_with_length():
    counter = TiktokenTokenCounter(encoding_name="cl100k_base")
    short = counter.count_text("hello")
    long = counter.count_text("hello " * 200)
    assert long > short


def test_tiktoken_counter_count_messages():
    counter = TiktokenTokenCounter(encoding_name="cl100k_base")
    messages = [HumanMessage(content="hi there"), AIMessage(content="hello back")]
    assert counter.count_messages(messages) > 0


def test_caching_counter_delegates_and_caches():
    inner = TiktokenTokenCounter(encoding_name="cl100k_base")
    caching = CachingTokenCounter(inner)
    text = "a repeated string of tokens"
    first = caching.count_text(text)
    second = caching.count_text(text)
    assert first == second
    assert caching.is_authoritative == inner.is_authoritative


def test_create_default_token_counter_never_raises():
    counter = create_default_token_counter(None)
    assert counter.count_text("some text") >= 0


def test_create_default_token_counter_resolves_explicit_model_name():
    class _FakeModel:
        model_name = "gpt-3.5-turbo"

    counter = create_default_token_counter(_FakeModel())
    assert counter.count_text("some text") >= 0
