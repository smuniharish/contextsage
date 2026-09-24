"""Unit tests for the preservation engine."""

from __future__ import annotations

from contextiq.context.decomposition import ContextDecomposer
from contextiq.core.models import PreservationLevel
from contextiq.importance.engine import ImportanceEngine
from contextiq.preservation.engine import PreservationEngine
from contextiq.relationships.engine import RelationshipEngine


def _pipeline(messages, token_counter):
    units = ContextDecomposer(token_counter).decompose(messages)
    units = ImportanceEngine().score(units)
    relationships = RelationshipEngine().analyze(units)
    classified = PreservationEngine().classify(units, relationships)
    return classified, relationships


def test_user_correction_is_must_preserve(correction_conversation, token_counter):
    classified, _ = _pipeline(correction_conversation, token_counter)
    correction_units = [u for u in classified if "instead of customer 123" in u.content.lower()]
    assert correction_units
    assert all(u.preservation is PreservationLevel.MUST_PRESERVE for u in correction_units)


def test_contradiction_participants_are_must_preserve(contradiction_conversation, token_counter):
    classified, relationships = _pipeline(contradiction_conversation, token_counter)
    assert relationships  # sanity: contradiction was actually detected
    flagged_ids = {r.source_unit_id for r in relationships} | {
        r.target_unit_id for r in relationships
    }
    for unit in classified:
        if unit.unit_id in flagged_ids:
            assert unit.preservation is PreservationLevel.MUST_PRESERVE


def test_repetitive_units_are_redundant_or_safe_to_drop(token_counter):
    from langchain_core.messages import ToolMessage

    # Repetition is detected at the unit (block) level, not the line level:
    # many near-duplicate ToolMessages (e.g. repeated heartbeat polls) should
    # be grouped and down-weighted, while a genuinely distinct unit is not.
    messages = [
        ToolMessage(
            content=f"2024-01-01T00:00:{i:02d} INFO heartbeat ok, seq={i}",
            tool_call_id=f"c{i}",
            id=f"t{i}",
        )
        for i in range(10)
    ]
    units = ContextDecomposer(token_counter).decompose(messages)
    scored = ImportanceEngine().score(units)
    classified = PreservationEngine().classify(scored, [])
    assert any(
        u.preservation in (PreservationLevel.REDUNDANT, PreservationLevel.SAFE_TO_DROP)
        for u in classified
    )


def test_extract_must_preserve_facts_includes_correction_referent(
    correction_conversation, token_counter
):
    classified, _ = _pipeline(correction_conversation, token_counter)
    facts = PreservationEngine().extract_must_preserve_facts(classified)
    assert any("456" in fact for fact in facts)


def test_maximum_preservation_policy_preserves_more_than_maximum_compression(token_counter):
    from langchain_core.messages import ToolMessage

    # Moderately important, unremarkable content: no correction/contradiction/error
    # signal, so classification falls back purely to the numeric importance
    # threshold, which is exactly what "policy" is meant to tune.
    messages = [
        ToolMessage(
            content="The nightly batch job processed 4,281 records without incident.",
            tool_call_id="c0",
            id="t0",
        )
    ]
    units = ContextDecomposer(token_counter).decompose(messages)
    scored = ImportanceEngine().score(units)

    preserving = PreservationEngine("maximum_preservation").classify(scored, [])
    compressing = PreservationEngine("maximum_compression").classify(scored, [])

    def _rank(level: PreservationLevel) -> int:
        order = [
            PreservationLevel.SAFE_TO_DROP,
            PreservationLevel.REDUNDANT,
            PreservationLevel.COMPRESSIBLE,
            PreservationLevel.SHOULD_PRESERVE,
            PreservationLevel.MUST_PRESERVE,
        ]
        return order.index(level)

    assert _rank(preserving[0].preservation) >= _rank(compressing[0].preservation)
