"""Unit tests for heterogeneous context decomposition."""

from __future__ import annotations

from contextsage.context.decomposition import ContextDecomposer
from contextsage.core.models import RegionKind


def test_decompose_splits_mixed_content_into_multiple_kinds(mixed_tool_message, token_counter):
    decomposer = ContextDecomposer(token_counter)
    units = decomposer.decompose([mixed_tool_message])
    kinds = {u.signals.kind for u in units}
    # The single ToolMessage must never collapse into one region/kind.
    assert len(units) > 1
    assert RegionKind.JSON in kinds
    assert any(u.signals.kind in (RegionKind.LOG, RegionKind.TEXT, RegionKind.ERROR) for u in units)


def test_decompose_ignores_blank_messages(token_counter):
    from langchain_core.messages import HumanMessage

    decomposer = ContextDecomposer(token_counter)
    units = decomposer.decompose([HumanMessage(content="   ")])
    assert units == []


def test_decompose_extracts_fenced_code_block(token_counter):
    from langchain_core.messages import AIMessage

    message = AIMessage(content="Here is a fix:\n```python\ndef f():\n    return 1\n```\nDone.")
    decomposer = ContextDecomposer(token_counter)
    units = decomposer.decompose([message])
    assert any(u.signals.kind == RegionKind.CODE for u in units)


def test_decompose_preserves_message_linkage(mixed_tool_message, token_counter):
    decomposer = ContextDecomposer(token_counter)
    units = decomposer.decompose([mixed_tool_message])
    assert all(u.message_id == "tool-1" for u in units)
    assert all(u.message_index == 0 for u in units)
