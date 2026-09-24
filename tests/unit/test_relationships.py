"""Unit tests for relationships/contradiction/correction detection."""

from __future__ import annotations

from contextsage.context.decomposition import ContextDecomposer
from contextsage.core.models import RelationType
from contextsage.importance.engine import ImportanceEngine
from contextsage.relationships.engine import RelationshipEngine, pair_tool_calls


def test_contradiction_detected_between_conflicting_status_values(
    contradiction_conversation, token_counter
):
    units = ContextDecomposer(token_counter).decompose(contradiction_conversation)
    relationships = RelationshipEngine().analyze(units)
    assert any(r.relation is RelationType.CONTRADICTS for r in relationships)


def test_no_contradiction_when_values_agree(token_counter):
    from langchain_core.messages import ToolMessage

    units = ContextDecomposer(token_counter).decompose(
        [
            ToolMessage(content="status=SUCCESS", tool_call_id="c1", id="t1"),
            ToolMessage(content="status=SUCCESS", tool_call_id="c2", id="t2"),
        ]
    )
    relationships = RelationshipEngine().analyze(units)
    assert not any(r.relation is RelationType.CONTRADICTS for r in relationships)


def test_correction_relationship_links_to_earlier_referent(correction_conversation, token_counter):
    units = ContextDecomposer(token_counter).decompose(correction_conversation)
    scored = ImportanceEngine().score(units)
    relationships = RelationshipEngine().analyze(scored)
    assert any(r.relation is RelationType.CORRECTED_BY for r in relationships)


def test_pair_tool_calls_pairs_ai_and_tool_messages(paired_tool_call_conversation):
    pairs = pair_tool_calls(paired_tool_call_conversation)
    assert "call-42" in pairs
    ai_id, tool_id = pairs["call-42"]
    assert ai_id == "a1"
    assert tool_id == "t1"


def test_pair_tool_calls_detects_orphaned_tool_message():
    from langchain_core.messages import ToolMessage

    pairs = pair_tool_calls([ToolMessage(content="result", tool_call_id="orphan", id="t1")])
    ai_id, tool_id = pairs["orphan"]
    assert ai_id is None
    assert tool_id == "t1"
