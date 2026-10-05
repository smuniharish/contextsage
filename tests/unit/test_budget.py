from __future__ import annotations

from typing import Any

import pytest

from contextsage import ConfigurationError
from contextsage._pipeline.budget import (
    DEFAULT_MAXIMUM_CONTEXT_TOKENS,
    Budget,
    Trigger,
    resolve_keep,
    resolve_maximum_context_tokens,
)
from tests.support.builders import profiled_model, summary_model


def budget(**overrides: object) -> Budget:
    values: dict[str, Any] = {
        "maximum_context_tokens": 10_000,
        "reserved_output_tokens": 1_000,
        "safety_margin": 0.1,
        "summarization_overhead_tokens": 500,
    }
    values.update(overrides)
    return Budget(**values)


class TestResolveMaximumContextTokens:
    def test_explicit_value_wins(self):
        assert resolve_maximum_context_tokens(profiled_model(50_000), 8_000) == 8_000

    def test_reads_the_model_profile(self):
        assert resolve_maximum_context_tokens(profiled_model(50_000), None) == 50_000

    def test_falls_back_without_a_profile(self):
        assert (
            resolve_maximum_context_tokens(summary_model(), None)
            == DEFAULT_MAXIMUM_CONTEXT_TOKENS
        )


class TestResolveKeep:
    @pytest.mark.parametrize("keep", [("messages", 20), ("tokens", 3_000)])
    def test_messages_and_tokens_are_kept_as_given(self, keep):
        assert resolve_keep(keep, 10_000) == keep

    def test_a_fraction_becomes_tokens_of_the_context_window(self):
        assert resolve_keep(("fraction", 0.3), 10_000) == ("tokens", 3_000)
        assert resolve_keep(("fraction", 1), 10_000) == ("tokens", 10_000)
        assert resolve_keep(("fraction", 0.00001), 10_000) == ("tokens", 1)

    @pytest.mark.parametrize(
        "keep",
        [
            ("messages", 0),
            ("tokens", -5),
            ("tokens", 1.5),
            ("messages", True),
            ("fraction", 0),
            ("fraction", 1.5),
            ("fraction", True),
            ("seconds", 3),
            ("messages",),
            "messages",
        ],
    )
    def test_malformed_values_are_rejected(self, keep):
        with pytest.raises(ConfigurationError, match="keep must be"):
            resolve_keep(keep, 10_000)

    @pytest.mark.parametrize("value", [0, -5, True, 1.5])
    def test_rejects_invalid_explicit_values(self, value):
        with pytest.raises(ConfigurationError, match="maximum_context_tokens"):
            resolve_maximum_context_tokens(summary_model(), value)

    def test_ignores_an_invalid_profile_value(self):
        assert (
            resolve_maximum_context_tokens(profiled_model(0), None)
            == DEFAULT_MAXIMUM_CONTEXT_TOKENS
        )


class TestBudget:
    def test_accounts_for_every_reservation(self):
        report = budget()
        assert report.safety_margin_tokens == 1_000
        assert report.available_tokens == 10_000 - 1_000 - 1_000 - 500

    @pytest.mark.parametrize(
        ("field", "value", "message"),
        [
            ("reserved_output_tokens", -1, "reserved_output_tokens"),
            ("reserved_output_tokens", True, "reserved_output_tokens"),
            ("summarization_overhead_tokens", -1, "summarization_overhead_tokens"),
            ("summarization_overhead_tokens", 2.5, "summarization_overhead_tokens"),
            ("safety_margin", 1.0, "safety_margin"),
            ("safety_margin", -0.1, "safety_margin"),
            ("safety_margin", False, "safety_margin"),
            ("safety_margin", "0.1", "safety_margin"),
        ],
    )
    def test_rejects_invalid_values(self, field, value, message):
        with pytest.raises(ConfigurationError, match=message):
            budget(**{field: value})

    def test_rejects_a_budget_without_room_for_input(self):
        with pytest.raises(ConfigurationError, match="no room for input"):
            budget(reserved_output_tokens=9_000, summarization_overhead_tokens=1_000)


class TestTrigger:
    def test_budget_mode_fires_only_on_overflow(self):
        trigger = Trigger(None, budget())
        assert trigger.evaluate(tokens=7_500, messages=3) is None
        decision = trigger.evaluate(tokens=7_600, messages=3)
        assert decision is not None
        assert decision.overflow_tokens == 100
        assert "7500-token input budget" in decision.reason

    def test_token_threshold(self):
        trigger = Trigger(("tokens", 1_000), budget())
        assert trigger.evaluate(tokens=999, messages=1) is None
        decision = trigger.evaluate(tokens=1_200, messages=1)
        assert decision is not None
        assert decision.overflow_tokens == 200
        assert decision.reason == "1200 tokens >= 1000"

    def test_message_threshold_reports_budget_overflow(self):
        trigger = Trigger(("messages", 5), budget())
        assert trigger.evaluate(tokens=10, messages=4) is None
        decision = trigger.evaluate(tokens=8_000, messages=5)
        assert decision is not None
        assert decision.reason == "5 messages >= 5"
        assert decision.overflow_tokens == 500

    def test_fraction_threshold_uses_the_context_window(self):
        trigger = Trigger(("fraction", 0.5), budget())
        assert trigger.evaluate(tokens=4_999, messages=1) is None
        decision = trigger.evaluate(tokens=5_000, messages=1)
        assert decision is not None
        assert decision.reason == "5000 tokens >= 5000"

    def test_clause_requires_every_condition(self):
        trigger = Trigger({"tokens": 100, "messages": 3}, budget())
        assert trigger.evaluate(tokens=500, messages=2) is None
        assert trigger.evaluate(tokens=50, messages=5) is None
        decision = trigger.evaluate(tokens=500, messages=3)
        assert decision is not None
        assert decision.reason == "500 tokens >= 100 and 3 messages >= 3"

    def test_list_requires_any_item(self):
        trigger = Trigger([("messages", 10), {"tokens": 100}], budget())
        assert trigger.evaluate(tokens=50, messages=2) is None
        assert trigger.evaluate(tokens=150, messages=2) is not None
        assert trigger.evaluate(tokens=50, messages=10) is not None

    @pytest.mark.parametrize(
        ("spec", "message"),
        [
            (("tokens",), "trigger tuple"),
            (("seconds", 5), "trigger tuple"),
            (("tokens", 0), "positive integer"),
            (("tokens", 1.5), "positive integer"),
            (("messages", True), "must be a number"),
            (("fraction", 0), "in \\(0, 1\\]"),
            (("fraction", 1.5), "in \\(0, 1\\]"),
            (("fraction", "half"), "must be a number"),
            ({}, "trigger clause"),
            ({"tokens": 10, "seconds": 1}, "trigger clause"),
            ([], "must not be empty"),
            ("tokens", "unsupported trigger"),
            (42, "unsupported trigger"),
        ],
    )
    def test_rejects_malformed_specs(self, spec, message):
        with pytest.raises(ConfigurationError, match=message):
            Trigger(spec, budget())
