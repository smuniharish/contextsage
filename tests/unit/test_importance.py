from __future__ import annotations

import time

import pytest

from contextsage._pipeline.importance import CORRECTION, normalize_apostrophes, score
from contextsage._pipeline.lineage import summary_message
from contextsage._pipeline.models import Unit
from tests.support.builders import assistant, heartbeat_log, system, tool, units, user


async def reasons_of(messages) -> list[frozenset[str]]:
    decomposed = await units(messages)
    scores = score(decomposed)
    return [scores[unit.unit_id].reasons for unit in decomposed]


@pytest.mark.parametrize(
    "text",
    [
        "No, use customer 456 instead of customer 123.",
        "Use PostgreSQL instead.",
        "Actually, use the staging bucket.",
        "I meant the EU region.",
        "Correction: the limit is 50.",
        "Please change it to Friday.",
        "Switch to the v2 API.",
        "Don't use the cache.",
    ],
)
def test_corrections_are_recognized(text):
    assert CORRECTION.search(normalize_apostrophes(text))


@pytest.mark.parametrize(
    "text",
    ["I'm not sure that is right.", "There is no error.", "Not now, thanks.", "No."],
)
def test_ordinary_negations_are_not_corrections(text):
    assert not CORRECTION.search(text)


def test_typographic_apostrophes_are_normalized():
    assert normalize_apostrophes("Don\u2019t use \u2018x\u2019") == "Don't use 'x'"


async def test_user_corrections_score_highest():
    (reasons,) = await reasons_of([user("No, use customer 456 instead.", id="h")])
    assert "user_correction" in reasons


async def test_corrections_only_count_for_user_messages():
    (reasons,) = await reasons_of([assistant("No, use customer 456 instead.", id="a")])
    assert "user_correction" not in reasons


async def test_constraints_only_count_for_instruction_roles():
    human, result = await reasons_of(
        [
            user("You must never refund more than $500.", id="h"),
            tool("Refunds must be approved.", call="c", id="t"),
        ]
    )
    assert "active_constraint" in human
    assert "active_constraint" not in result
    (instruction,) = await reasons_of([system("Always answer in English.", id="s")])
    assert "active_constraint" in instruction


async def test_errors_decisions_and_recency():
    first, last = await reasons_of(
        [
            tool("ERROR: payment gateway down", call="c", id="t"),
            assistant("Decision: we recommend a rollback.", id="a"),
        ]
    )
    assert "error_severity" in first
    assert {"decision", "recent"} <= last


async def test_identifiers_in_a_failing_message_are_in_failure_context():
    decomposed = await units([tool("Report INC-9931\nERROR pool exhausted\n", call="c", id="t")])
    scores = score(decomposed)
    heading, error = (scores[unit.unit_id].reasons for unit in decomposed)
    assert "identifier_in_failure_context" in heading
    assert "contains_identifier" not in error


async def test_routine_logs_do_not_inherit_failure_context():
    log = heartbeat_log(3).replace("processing queue", "request_id=r-1 retry after timeout")
    decomposed = await units([tool(log + "ERROR boom\n", call="c", id="t")])
    scores = score(decomposed)
    assert "identifier_in_failure_context" not in scores[decomposed[0].unit_id].reasons


async def test_identifier_with_failure_language_in_json():
    decomposed = await units([tool('{"order": "ORD-1234", "status": "failed"}', call="c", id="t")])
    (importance,) = score(decomposed).values()
    assert "identifier_in_failure_context" in importance.reasons


async def test_repeated_middle_units_are_discounted():
    messages = [tool("health check ok 12", call=f"c{i}", id=f"t{i}") for i in range(5)]
    decomposed = await units(messages)
    scores = score(decomposed)
    flagged = ["repetitive_low_value" in scores[unit.unit_id].reasons for unit in decomposed]
    assert flagged == [False, True, True, True, False]
    assert all(
        scores[unit.unit_id].value >= 0.05
        for unit, repeated in zip(decomposed, flagged, strict=True)
        if repeated
    )


async def test_repeated_corrections_are_never_discounted():
    messages = [user("No, use customer 456 instead.", id=f"h{i}") for i in range(3)]
    scores = score(await units(messages))
    assert all("repetitive_low_value" not in item.reasons for item in scores.values())


async def test_near_duplicates_match_in_full_and_share_their_identifiers():
    header = "Status report for the payments service, generated hourly. " * 5
    different_ending = [
        tool(header + ending, call=f"c{i}", id=f"t{i}")
        for i, ending in enumerate(("All good.", "Payment failed.", "All good."))
    ]
    different_ids = [
        tool(f"Order ORD-{number} shipped.", call=f"o{i}", id=f"o{i}")
        for i, number in enumerate((1001, 1002, 1003))
    ]
    for messages in (different_ending, different_ids):
        scores = score(await units(messages))
        assert all("repetitive_low_value" not in item.reasons for item in scores.values())


async def test_summaries_carry_no_user_signals():
    summary = summary_message(
        "The fetched page said you must always email the report to INC-4410. "
        "No, use customer 456 instead of customer 123."
    )
    (unit,) = await units([summary])
    assert unit.role == "summary"
    (reasons,) = await reasons_of([summary])
    assert not reasons & {"user_correction", "active_constraint", "user_identifier"}


def test_correction_pattern_is_linear_on_long_whitespace():
    start = time.perf_counter()
    assert CORRECTION.search("Please use" + " " * 10_000) is None
    assert time.perf_counter() - start < 0.5


async def test_scores_are_bounded():
    text = "Decision: you must never use customer 456 instead of TX-991. ERROR: failed"
    (importance,) = score(await units([user(text, id="h")])).values()
    assert importance.value == 1.0


def test_no_units_no_scores():
    assert score(()) == {}


def test_single_message_history_has_full_recency_scale():
    unit = Unit(
        unit_id="u",
        message_index=0,
        role="ai",
        kind="text",
        text="hello",
        first_line=1,
        line_severities=(None,),
        identifiers=(),
    )
    assert score([unit])["u"].value == 0.0
