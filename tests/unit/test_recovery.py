"""Unit tests for the recovery manager."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from contextsage.core.models import ValidationFinding, ValidationResult
from contextsage.recovery.manager import RecoveryManager


def test_recover_from_validation_failure_restates_missing_facts():
    manager = RecoveryManager()
    validation_result = ValidationResult(
        passed=False,
        findings=(
            ValidationFinding(
                severity="critical", description="missing fact", fact="transaction_id=TX-991"
            ),
        ),
    )
    messages, outcome = manager.recover_from_validation_failure(
        messages=[AIMessage(content="A summary that lost something.")],
        validation_result=validation_result,
        must_preserve_facts=("transaction_id=TX-991",),
    )
    assert outcome.recovered is True
    assert outcome.fallback_used is True
    assert any("TX-991" in str(m.content) for m in messages)


def test_recover_from_validation_failure_with_no_facts_to_restate():
    manager = RecoveryManager()
    validation_result = ValidationResult(
        passed=False,
        findings=(ValidationFinding(severity="critical", description="orphaned tool message"),),
    )
    messages, outcome = manager.recover_from_validation_failure(
        messages=[AIMessage(content="summary")],
        validation_result=validation_result,
        must_preserve_facts=(),
    )
    assert outcome.recovered is False
    assert outcome.strategy == "none_applicable"


def test_recover_from_summarization_failure_falls_back_to_trim():
    manager = RecoveryManager()
    original = [HumanMessage(content=f"message {i}", id=f"m{i}") for i in range(10)]
    recovered, outcome = manager.recover_from_summarization_failure(
        original_messages=original,
        keep_count=3,
        must_preserve_facts=("critical fact",),
        error=RuntimeError("timeout"),
    )
    assert outcome.recovered is True
    assert outcome.fallback_used is True
    assert "critical fact" in str(recovered[0].content)
    # Last 3 original messages must still be present, in order.
    assert [m.id for m in recovered[-3:]] == ["m7", "m8", "m9"]
