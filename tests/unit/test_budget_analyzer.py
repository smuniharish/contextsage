"""Unit tests for the context budget analyzer."""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from contextsage.budget.analyzer import BudgetAnalyzer, BudgetConfig, infer_max_context_tokens
from contextsage.exceptions import BudgetError


def test_budget_config_rejects_invalid_values():
    with pytest.raises(BudgetError):
        BudgetConfig(maximum_context_tokens=0)
    with pytest.raises(BudgetError):
        BudgetConfig(safety_margin_fraction=1.5)
    with pytest.raises(BudgetError):
        BudgetConfig(reserved_output_tokens=-1)


def test_budget_analyzer_reports_explicit_fields(token_counter):
    config = BudgetConfig(
        maximum_context_tokens=1000,
        reserved_output_tokens=100,
        safety_margin_fraction=0.1,
        summarization_overhead_tokens=50,
    )
    analyzer = BudgetAnalyzer(token_counter, config)
    report = analyzer.analyze(
        [HumanMessage(content="hello world " * 10)],
        system_prompt="you are a helpful agent",
        tool_schemas=["schema-a", "schema-b"],
    )
    assert report.maximum_context_tokens == 1000
    assert report.reserved_output_tokens == 100
    assert report.safety_margin_tokens == 100
    assert report.summarization_overhead_tokens == 50
    assert report.system_tokens > 0
    assert report.tool_schema_tokens > 0
    assert report.current_input_tokens > 0
    assert report.available_input_tokens == max(
        1000 - 100 - report.system_tokens - report.tool_schema_tokens - 100 - 50, 0
    )


def test_budget_report_overflow_and_utilization(token_counter):
    config = BudgetConfig(
        maximum_context_tokens=50, reserved_output_tokens=0, safety_margin_fraction=0.0
    )
    analyzer = BudgetAnalyzer(token_counter, config)
    report = analyzer.analyze([HumanMessage(content="word " * 500)])
    assert report.is_over_budget is True
    assert report.overflow_tokens > 0
    assert report.utilization > 1.0


def test_budget_report_within_budget(token_counter):
    config = BudgetConfig(
        maximum_context_tokens=100_000, reserved_output_tokens=0, safety_margin_fraction=0.0
    )
    analyzer = BudgetAnalyzer(token_counter, config)
    report = analyzer.analyze([HumanMessage(content="hi")])
    assert report.is_over_budget is False
    assert report.overflow_tokens == 0


def test_infer_max_context_tokens_falls_back_without_profile():
    class DummyModel:
        pass

    assert infer_max_context_tokens(DummyModel(), default=42) == 42


def test_infer_max_context_tokens_uses_profile_when_present():
    class DummyModel:
        profile = {"max_input_tokens": 12345}

    assert infer_max_context_tokens(DummyModel()) == 12345
