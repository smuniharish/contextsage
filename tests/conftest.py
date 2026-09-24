"""Shared pytest fixtures for the ContextSage test suite."""

from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from contextsage.budget.tokens import TiktokenTokenCounter


@pytest.fixture
def token_counter() -> TiktokenTokenCounter:
    # Pin to a specific, already-resolvable encoding (no model-name lookup)
    # so tests are fast and deterministic regardless of network access.
    return TiktokenTokenCounter(encoding_name="cl100k_base")


@pytest.fixture
def mixed_tool_message() -> ToolMessage:
    """A single ToolMessage mixing prose, JSON, and repeated log lines."""
    body = (
        "The database migration completed with some issues.\n"
        + json.dumps(
            {
                "status": "failed",
                "transaction_id": "TX-991",
                "errors": ["connection pool exhausted"],
            }
        )
        + "\n"
        + ("INFO heartbeat ok\n" * 40)
        + "ERROR root cause: PostgreSQL connection pool exhaustion\n"
    )
    return ToolMessage(content=body, tool_call_id="call-1", id="tool-1")


@pytest.fixture
def correction_conversation() -> list:
    return [
        HumanMessage(content="Please process the order for customer 123.", id="h1"),
        AIMessage(content="Okay, processing customer 123.", id="a1"),
        HumanMessage(content="No, use customer 456 instead of customer 123.", id="h2"),
        AIMessage(content="Understood, switching to customer 456.", id="a2"),
    ]


@pytest.fixture
def contradiction_conversation() -> list:
    return [
        ToolMessage(content="status=SUCCESS", tool_call_id="c1", id="t1"),
        ToolMessage(content="status=FAILED", tool_call_id="c2", id="t2"),
    ]


@pytest.fixture
def paired_tool_call_conversation() -> list:
    return [
        HumanMessage(content="Look up order 42.", id="h1"),
        AIMessage(
            content="",
            id="a1",
            tool_calls=[{"id": "call-42", "name": "lookup_order", "args": {"order_id": 42}}],
        ),
        ToolMessage(content="Order 42: shipped", tool_call_id="call-42", id="t1"),
        AIMessage(content="Order 42 has shipped.", id="a2"),
    ]
