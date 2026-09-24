"""Unit tests for the summarization planner."""

from __future__ import annotations

from contextiq.context.decomposition import ContextDecomposer
from contextiq.importance.engine import ImportanceEngine
from contextiq.planning.planner import SummarizationPlanner
from contextiq.preservation.engine import PreservationEngine
from contextiq.relationships.engine import RelationshipEngine


def _classified_units(messages, token_counter):
    units = ContextDecomposer(token_counter).decompose(messages)
    units = ImportanceEngine().score(units)
    relationships = RelationshipEngine().analyze(units)
    return PreservationEngine().classify(units, relationships)


def test_plan_not_required_returns_empty_plan(token_counter, correction_conversation):
    units = _classified_units(correction_conversation, token_counter)
    plan = SummarizationPlanner().plan(
        units,
        required=False,
        trigger_reason="within budget",
        overflow_tokens=0,
        must_preserve_facts=(),
    )
    assert plan.required is False
    assert plan.targets == ()


def test_plan_separates_deterministic_semantic_and_preserve_targets(
    mixed_tool_message, token_counter
):
    units = _classified_units([mixed_tool_message], token_counter)
    plan = SummarizationPlanner().plan(
        units,
        required=True,
        trigger_reason="overflow",
        overflow_tokens=100,
        must_preserve_facts=("TX-991",),
    )
    assert plan.required is True
    actions = {t.action for t in plan.targets}
    assert actions <= {"transform_deterministic", "semantic_summarize", "preserve_untouched"}


def test_plan_protects_paired_tool_call_messages(paired_tool_call_conversation, token_counter):
    units = _classified_units(paired_tool_call_conversation, token_counter)
    plan = SummarizationPlanner().plan(
        units,
        required=True,
        trigger_reason="overflow",
        overflow_tokens=10,
        must_preserve_facts=(),
        protected_message_ids=("a1", "t1"),
    )
    preserve_target = next(t for t in plan.targets if t.action == "preserve_untouched")
    protected_units = [u for u in units if u.message_id in ("a1", "t1")]
    assert all(u.unit_id in preserve_target.unit_ids for u in protected_units)
