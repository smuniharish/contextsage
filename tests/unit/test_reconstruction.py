"""Unit tests for message reconstruction safety."""

from __future__ import annotations

from dataclasses import replace

from langchain_core.messages import HumanMessage

from contextsage.context.decomposition import ContextDecomposer
from contextsage.core.reconstruction import apply_transformed_units, content_signal_counts


def test_untouched_units_return_the_same_message_object(token_counter):
    message = HumanMessage(content="hello world", id="h1")
    units = ContextDecomposer(token_counter).decompose([message])
    rebuilt = apply_transformed_units([message], units)
    assert rebuilt[0] is message


def test_transformed_units_rebuild_message_content(token_counter):
    message = HumanMessage(content="hello world", id="h1")
    units = ContextDecomposer(token_counter).decompose([message])
    transformed = [
        replace(u, content="HELLO", metadata={**u.metadata, "contextsage_transformed": True})
        for u in units
    ]
    rebuilt = apply_transformed_units([message], transformed)
    assert rebuilt[0] is not message
    assert rebuilt[0].content == "HELLO"
    assert rebuilt[0].id == "h1"


def test_content_signal_counts_aggregates_by_kind(mixed_tool_message, token_counter):
    units = ContextDecomposer(token_counter).decompose([mixed_tool_message])
    counts = content_signal_counts(units)
    assert sum(counts.values()) == len(units)
