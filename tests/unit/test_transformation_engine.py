"""Unit tests for the deterministic transformation engine."""

from __future__ import annotations

from contextiq.context.decomposition import ContextDecomposer
from contextiq.core.models import PlanTarget, RegionKind, SummarizationPlan
from contextiq.transformation.engine import ContextTransformationEngine


def test_transform_reduces_log_heavy_units(token_counter):
    from langchain_core.messages import ToolMessage

    lines = [f"2024-01-01T00:00:{i:02d} INFO heartbeat ok" for i in range(59)]
    lines.append("2024-01-01T00:01:00 ERROR root cause: disk full")
    body = "\n".join(lines) + "\n"
    units = ContextDecomposer(token_counter).decompose(
        [ToolMessage(content=body, tool_call_id="c1", id="t1")]
    )
    log_units = [u for u in units if u.signals.kind == RegionKind.LOG]
    assert log_units
    plan = SummarizationPlan(
        required=True,
        trigger_reason="test",
        overflow_tokens=10,
        targets=(
            PlanTarget(
                unit_ids=tuple(u.unit_id for u in log_units),
                action="transform_deterministic",
                reason="test",
            ),
        ),
    )
    outcome = ContextTransformationEngine(token_counter).transform(units, plan)
    assert outcome.transformed_unit_ids
    assert outcome.tokens_saved >= 0


def test_transform_leaves_non_targeted_units_untouched(token_counter):
    from langchain_core.messages import HumanMessage

    units = ContextDecomposer(token_counter).decompose(
        [HumanMessage(content="just plain text", id="h1")]
    )
    plan = SummarizationPlan(required=True, trigger_reason="test", overflow_tokens=1)
    outcome = ContextTransformationEngine(token_counter).transform(units, plan)
    assert outcome.transformed_unit_ids == ()
    assert outcome.units[0].content == "just plain text"


def test_transform_fails_safe_when_transformer_raises(monkeypatch, token_counter):
    from langchain_core.messages import ToolMessage

    from contextiq.exceptions import TransformationError

    units = ContextDecomposer(token_counter).decompose(
        [ToolMessage(content='{"a": 1}', tool_call_id="c1", id="t1")]
    )
    json_units = [u for u in units if u.signals.kind == RegionKind.JSON]
    assert json_units

    def _boom(_text: str) -> str:
        raise TransformationError("boom")

    import contextiq.transformation.engine as engine_module

    monkeypatch.setitem(engine_module._TRANSFORMERS, RegionKind.JSON, _boom)

    plan = SummarizationPlan(
        required=True,
        trigger_reason="test",
        overflow_tokens=1,
        targets=(
            PlanTarget(
                unit_ids=tuple(u.unit_id for u in json_units),
                action="transform_deterministic",
                reason="test",
            ),
        ),
    )
    outcome = ContextTransformationEngine(token_counter).transform(units, plan)
    # A transformer that raises TransformationError must never corrupt the
    # unit; the engine's fail-safe path leaves the original content intact.
    assert outcome.units[0].content == '{"a": 1}'
    assert outcome.units[0].unit_id in outcome.failed_unit_ids
