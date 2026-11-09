from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

from contextsage import (
    BalancedPolicy,
    Fact,
    MaximumCompressionPolicy,
    MaximumPreservationPolicy,
)
from contextsage._pipeline.importance import score
from contextsage._pipeline.models import Importance, Preservation, Unit
from contextsage._pipeline.preservation import (
    _CORRECTED_VALUE,
    _REPLACED_VALUE,
    _sentence,
    classify,
    extract_facts,
)
from contextsage._pipeline.relationships import find_contradictions
from contextsage._pipeline.validation import validate
from tests.support.builders import assistant, prepare, tool, units, user

if TYPE_CHECKING:
    from contextsage import PreservationPolicy


async def analyze(messages, policy: PreservationPolicy | None = None):
    analysis = (await prepare(messages, policy)).analysis
    return analysis.units, analysis.preservation, analysis.facts


def unit(text: str = "text", role: str = "assistant", index: int = 0) -> Unit:
    return Unit(
        unit_id=f"u{index}",
        message_index=index,
        role=role,
        kind="text",
        text=text,
        first_line=1,
        line_severities=(None,),
        identifiers=(),
    )


async def test_corrections_are_must_preserve_with_the_corrected_value_required():
    decomposed, levels, facts = await analyze(
        [
            user("Process the order for customer 123.", id="h1"),
            user("I'm not sure. No, use customer 456 instead of customer 123.", id="h2"),
        ]
    )
    assert levels[decomposed[1].unit_id] is Preservation.MUST
    assert (
        Fact(
            'User correction: "No, use customer 456 instead of customer 123."',
            ("customer 456",),
        )
        in facts
    )
    assert all(fact.statement != "customer 123" for fact in facts)
    assert all("sure" not in fact.required for fact in facts)


async def test_corrections_without_an_extractable_value_require_the_sentence():
    _, _, facts = await analyze([user("Correction: the limit is 50", id="h")])
    assert (
        Fact(
            'User correction: "Correction: the limit is 50"',
            ("Correction: the limit is 50",),
        )
        in facts
    )


async def test_constraints_become_instruction_facts():
    _, _, facts = await analyze(
        [user("Hi there.\nYou must never refund more than 500 dollars.", id="h")]
    )
    assert (
        Fact(
            'User instruction: "You must never refund more than 500 dollars."',
            ("You must never refund more than 500 dollars.",),
        )
        in facts
    )


async def test_maximum_compression_keeps_old_instructions_compressible():
    messages = [
        user("You must always cite sources.", id="h0"),
        *(assistant(f"Answer {index}.", id=f"a{index}") for index in range(5)),
    ]
    decomposed, levels, _ = await analyze(messages, MaximumCompressionPolicy())
    assert levels[decomposed[0].unit_id] is Preservation.SHOULD
    decomposed, levels, _ = await analyze(messages, BalancedPolicy())
    assert levels[decomposed[0].unit_id] is Preservation.MUST


async def test_contradictions_are_must_preserve_and_become_facts():
    messages = [
        tool("status=SUCCESS", call="c1", id="t1"),
        tool("status=FAILED", call="c2", id="t2"),
    ]
    decomposed, levels, facts = await analyze(messages)
    assert {levels[item.unit_id] for item in decomposed} == {Preservation.MUST}
    assert (
        Fact(
            "Conflicting values reported for status: SUCCESS (earlier) vs FAILED (later)",
            ("SUCCESS", "FAILED"),
        )
        in facts
    )


async def test_identifiers_in_failure_context_are_facts():
    _, _, facts = await analyze(
        [tool("Transaction TX-991 failed: card declined", call="c", id="t")]
    )
    assert Fact("TX-991", ("TX-991",)) in facts


async def test_facts_are_unique():
    _, _, facts = await analyze(
        [
            tool("TX-991 failed", call="c1", id="t1"),
            tool("TX-991 failed again", call="c2", id="t2"),
        ]
    )
    statements = [fact.statement for fact in facts]
    assert statements.count("TX-991") == 1


def test_policies_change_the_numeric_thresholds():
    item = unit()
    importance = {item.unit_id: Importance(0.62, frozenset())}
    levels = [
        classify([item], importance, (), policy)[item.unit_id]
        for policy in (MaximumPreservationPolicy(), BalancedPolicy(), MaximumCompressionPolicy())
    ]
    assert levels == [Preservation.MUST, Preservation.SHOULD, Preservation.COMPRESSIBLE]


def test_error_severity_uses_the_policy_error_threshold():
    item = unit()
    importance = {item.unit_id: Importance(0.5, frozenset({"error_severity"}))}
    assert (
        classify([item], importance, (), MaximumPreservationPolicy())[item.unit_id]
        is Preservation.MUST
    )
    assert classify([item], importance, (), BalancedPolicy())[item.unit_id] is Preservation.SHOULD


def test_repetitive_units_are_compressible_unless_structurally_required():
    item = unit()
    repetitive = {item.unit_id: Importance(0.95, frozenset({"repetitive_low_value"}))}
    assert (
        classify([item], repetitive, (), MaximumPreservationPolicy())[item.unit_id]
        is Preservation.COMPRESSIBLE
    )
    failing = {
        item.unit_id: Importance(
            0.1, frozenset({"repetitive_low_value", "identifier_in_failure_context"})
        )
    }
    assert classify([item], failing, (), BalancedPolicy())[item.unit_id] is Preservation.MUST


async def test_extract_facts_skips_units_that_are_not_must_preserve():
    decomposed = await units([assistant("TX-991 is fine", id="a")])
    importance = score(decomposed)
    levels = {item.unit_id: Preservation.SHOULD for item in decomposed}
    contradictions = find_contradictions(decomposed)
    assert extract_facts(decomposed, importance, levels, contradictions, carried=()) == ()


async def test_carried_facts_come_first_unless_a_correction_replaced_them():
    decomposed = await units([user("No, use customer 456 instead of customer 123.", id="h")])
    importance = score(decomposed)
    levels = classify(decomposed, importance, (), BalancedPolicy())
    old_customer = Fact("customer 123", ("customer 123",))
    incident = Fact("INC-7731", ("INC-7731",))
    facts = extract_facts(decomposed, importance, levels, (), carried=(old_customer, incident))
    assert facts[0] == incident
    assert old_customer not in facts


async def test_long_sentences_are_trimmed_at_a_word_boundary():
    text = "No, use " + "very " * 80 + "long value instead."
    message = user(text, id="h")
    _, _, facts = await analyze([message])
    (correction,) = [fact for fact in facts if fact.statement.startswith("User correction")]
    assert len(correction.statement) <= len('User correction: ""') + 200
    assert correction.statement.endswith('very"')
    assert validate([message], (correction,)).missing == ()


async def test_long_sentences_narrow_to_the_words_around_the_match():
    text = "note " * 100 + "you must never refund more than 500 dollars"
    message = user(text, id="h")
    _, _, facts = await analyze([message])
    (instruction,) = [fact for fact in facts if fact.statement.startswith("User instruction")]
    (sentence,) = instruction.required
    assert sentence.endswith("you must never refund more than 500 dollars")
    assert len(sentence) <= 200
    assert validate([message], (instruction,)).missing == ()


async def test_a_matched_word_longer_than_the_limit_gives_no_sentence():
    text = "x" * 300
    match = re.match("x", text)
    assert match is not None
    assert _sentence(text, match) is None
    long_words = f"{'x' * 300}-must {'x' * 300}-instead of y"
    _, _, facts = await analyze([user(long_words, id="h")])
    assert not any(fact.statement.startswith("User ") for fact in facts)


def test_value_patterns_are_linear_on_long_whitespace():
    spaces = " " * 10_000
    start = time.perf_counter()
    assert _REPLACED_VALUE.search(f"instead of{spaces}{'x' * 70}") is None
    assert _CORRECTED_VALUE.search(f"use{spaces}{'x' * 70}") is None
    assert time.perf_counter() - start < 0.5
