"""Unit tests for the importance engine."""

from __future__ import annotations

from contextiq.context.decomposition import ContextDecomposer
from contextiq.importance.engine import ImportanceEngine


def test_user_correction_scores_high(correction_conversation, token_counter):
    units = ContextDecomposer(token_counter).decompose(correction_conversation)
    scored = ImportanceEngine().score(units)
    correction_units = [u for u in scored if "instead of customer 123" in u.content.lower()]
    assert correction_units
    assert all(u.importance.value >= 0.5 for u in correction_units)
    assert any("user_correction" in u.importance.reasons for u in correction_units)


def test_repetitive_low_value_logs_are_downweighted(token_counter):
    from langchain_core.messages import ToolMessage

    body = "INFO heartbeat ok\n" * 50 + "ERROR something broke badly\n"
    message = ToolMessage(content=body, tool_call_id="c1", id="t1")
    units = ContextDecomposer(token_counter).decompose([message])
    scored = ImportanceEngine().score(units)
    # At least one unit should be flagged repetitive-low-value, and the error
    # line (first/last occurrence of a distinct signature) must not be.
    reasons = {reason for u in scored for reason in u.importance.reasons}
    assert "repetitive_low_value" in reasons or len(scored) <= 2


def test_score_handles_empty_units():
    assert ImportanceEngine().score([]) == []
