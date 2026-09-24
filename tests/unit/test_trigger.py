"""Unit tests for trigger evaluation (bridges public `trigger=` config to planning)."""

from __future__ import annotations

import pytest

from contextsage.core.models import BudgetReport
from contextsage.exceptions import PlanningError
from contextsage.planning.trigger import evaluate_trigger


def _report(current_input_tokens: int, maximum_context_tokens: int = 1000) -> BudgetReport:
    return BudgetReport(
        maximum_context_tokens=maximum_context_tokens,
        reserved_output_tokens=0,
        system_tokens=0,
        tool_schema_tokens=0,
        current_input_tokens=current_input_tokens,
        safety_margin_tokens=0,
    )


def test_tokens_trigger_fires_when_over_threshold():
    decision = evaluate_trigger(("tokens", 100), budget=_report(150), message_count=5)
    assert decision.required is True
    assert decision.overflow_tokens == 50


def test_tokens_trigger_does_not_fire_under_threshold():
    decision = evaluate_trigger(("tokens", 100), budget=_report(50), message_count=5)
    assert decision.required is False
    assert decision.overflow_tokens == 0


def test_messages_trigger_fires_on_count():
    decision = evaluate_trigger(("messages", 3), budget=_report(10), message_count=5)
    assert decision.required is True


def test_messages_trigger_does_not_fire_under_count():
    decision = evaluate_trigger(("messages", 30), budget=_report(10), message_count=5)
    assert decision.required is False


def test_fraction_trigger():
    decision = evaluate_trigger(("fraction", 0.5), budget=_report(600, 1000), message_count=1)
    assert decision.required is True
    decision = evaluate_trigger(("fraction", 0.9), budget=_report(600, 1000), message_count=1)
    assert decision.required is False


def test_none_trigger_falls_back_to_budget_overflow():
    over = _report(current_input_tokens=2000, maximum_context_tokens=1000)
    decision = evaluate_trigger(None, budget=over, message_count=1)
    assert decision.required is True
    assert decision.overflow_tokens == over.overflow_tokens

    under = _report(current_input_tokens=10, maximum_context_tokens=1000)
    decision = evaluate_trigger(None, budget=under, message_count=1)
    assert decision.required is False


def test_unsupported_trigger_kind_raises():
    with pytest.raises(PlanningError):
        evaluate_trigger(("unknown", 1), budget=_report(10), message_count=1)
