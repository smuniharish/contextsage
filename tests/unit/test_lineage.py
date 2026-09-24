"""Unit tests for lineage tracking."""

from __future__ import annotations

from contextiq.lineage.manager import (
    CONTEXTIQ_SUMMARY_ID_PREFIX,
    LineageManager,
    find_prior_summary_ids,
)


def test_next_summary_id_has_stable_prefix():
    manager = LineageManager()
    summary_id = manager.next_summary_id()
    assert summary_id.startswith(CONTEXTIQ_SUMMARY_ID_PREFIX)


def test_record_and_get_round_trip():
    manager = LineageManager()
    summary_id = manager.next_summary_id()
    lineage = manager.record(
        summary_id=summary_id,
        source_message_ids=("m1", "m2"),
        source_summary_ids=(),
        input_tokens=1000,
        prepared_tokens=800,
        summary_tokens=200,
        selected_target_count=2,
        preservation_unit_count=1,
        validation_status="passed",
        recovery_status="none_needed",
        fallback_used=False,
    )
    assert manager.get(summary_id) is lineage
    assert lineage.generation == 1
    assert lineage.compression_ratio == 0.2


def test_generation_increments_when_summarizing_a_summary():
    manager = LineageManager()
    first_id = manager.next_summary_id()
    manager.record(
        summary_id=first_id,
        source_message_ids=("m1",),
        source_summary_ids=(),
        input_tokens=100,
        prepared_tokens=100,
        summary_tokens=50,
        selected_target_count=1,
        preservation_unit_count=0,
        validation_status="passed",
        recovery_status="none_needed",
        fallback_used=False,
    )
    second_id = manager.next_summary_id()
    second = manager.record(
        summary_id=second_id,
        source_message_ids=(first_id, "m2"),
        source_summary_ids=(first_id,),
        input_tokens=200,
        prepared_tokens=200,
        summary_tokens=80,
        selected_target_count=1,
        preservation_unit_count=0,
        validation_status="passed",
        recovery_status="none_needed",
        fallback_used=False,
    )
    assert second.generation == 2


def test_find_prior_summary_ids_filters_non_summary_ids():
    manager = LineageManager()
    summary_id = manager.next_summary_id()
    found = find_prior_summary_ids((summary_id, "regular-message-id", None))
    assert found == (summary_id,)
