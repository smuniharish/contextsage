"""Unit tests for the summary validator."""

from __future__ import annotations

from langchain_core.messages import AIMessage, ToolMessage

from contextsage.core.models import Relationship, RelationType
from contextsage.validation.validator import SummaryValidator


def test_validate_passes_when_all_facts_present():
    result = SummaryValidator().validate(
        new_messages=[AIMessage(content="Customer is now 456, per your correction.")],
        must_preserve_facts=("456",),
    )
    assert result.passed is True


def test_validate_fails_when_fact_missing():
    result = SummaryValidator().validate(
        new_messages=[AIMessage(content="Payment service experienced some errors.")],
        must_preserve_facts=(
            "error_count=183",
            "root_cause: PostgreSQL connection pool exhaustion",
        ),
    )
    assert result.passed is False
    assert len(result.critical_findings) == 2


def test_validate_detects_orphaned_tool_message():
    result = SummaryValidator().validate(
        new_messages=[ToolMessage(content="result", tool_call_id="orphan", id="t1")],
        must_preserve_facts=(),
    )
    assert result.passed is False
    assert any("orphaned" in f.description for f in result.critical_findings)


def test_validate_fails_when_contradiction_collapsed():
    relationship = Relationship(
        source_unit_id="u1",
        target_unit_id="u2",
        relation=RelationType.CONTRADICTS,
        metadata={"key": "status", "value_a": "success", "value_b": "failed"},
    )
    result = SummaryValidator().validate(
        new_messages=[AIMessage(content="The operation completed successfully.")],
        must_preserve_facts=(),
        contradiction_relationships=(relationship,),
    )
    assert result.passed is False


def test_validate_passes_when_both_contradiction_values_present():
    relationship = Relationship(
        source_unit_id="u1",
        target_unit_id="u2",
        relation=RelationType.CONTRADICTS,
        metadata={"key": "status", "value_a": "success", "value_b": "failed"},
    )
    result = SummaryValidator().validate(
        new_messages=[
            AIMessage(content="Source A reported success, but source B reported failed.")
        ],
        must_preserve_facts=(),
        contradiction_relationships=(relationship,),
    )
    assert result.passed is True
