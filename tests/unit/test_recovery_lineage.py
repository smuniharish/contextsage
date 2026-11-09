from __future__ import annotations

from contextsage import Fact, Message, SummaryLineage, TokenizerTokenCounter
from contextsage._pipeline.lineage import (
    carried_facts,
    new_summary_id,
    replaced_summaries,
    stamp,
    summary_message,
)
from contextsage._pipeline.recovery import (
    FACTS_HEADING,
    FALLBACK_NOTICE,
    REQUEST_HEADING,
    facts_block,
    fallback,
    restate,
)
from contextsage._pipeline.validation import orphaned_tool_results, validate
from tests.support.builders import assistant, system, tool, user

FACTS = (Fact("TX-991", ("TX-991",)), Fact("User correction: use 456", ("456",)))
COUNTER = TokenizerTokenCounter()


def missing(window):
    return validate(window, FACTS).missing


def tool_turn(index: int) -> list[Message]:
    return [
        assistant(id=f"a{index}", calls=(f"c{index}",)),
        tool(f"result {index}", call=f"c{index}", id=f"t{index}"),
    ]


def summary(text: str, summary_id: str = "s1", **lineage) -> Message:
    return stamp(
        summary_message(text),
        summary_id=summary_id,
        generation=lineage.get("generation", 1),
        source_summary_ids=lineage.get("source_summary_ids", ()),
        facts=lineage.get("facts", ()),
    )


def test_facts_block():
    assert facts_block(FACTS) == f"{FACTS_HEADING}\n- TX-991\n- User correction: use 456"


def test_facts_block_states_each_fact_once():
    identifier = Fact("customer 456", ("customer 456",))
    correction = Fact('User correction: "use customer 456 instead"', ("456",))
    longer, shorter = Fact("ORD-12", ("ORD-12",)), Fact("ORD-1", ("ORD-1",))
    assert facts_block((identifier, correction, longer, shorter)) == (
        f'{FACTS_HEADING}\n- User correction: "use customer 456 instead"\n- ORD-12\n- ORD-1'
    )


def test_restate_appends_to_the_summary_message():
    messages = [summary("Here is a summary.", facts=FACTS), user("next", id="h")]
    restated = restate(messages, FACTS[:1])
    assert restated[0].content == f"Here is a summary.\n\n{FACTS_HEADING}\n- TX-991"
    assert restated[0].id == "s1"
    assert restated[0].lineage == messages[0].lineage
    assert restated[1] is messages[1]


def test_restate_inserts_a_summary_after_system_messages():
    messages = [system("rules", id="s"), user("next", id="h")]
    restated = restate(messages, FACTS[:1])
    assert [message.role for message in restated] == ["system", "user", "user"]
    assert restated[1].is_summary


def test_restate_never_rewrites_a_summary_that_is_not_rewritable():
    frozen = Message("user", "s", id="s1", rewritable=False, lineage=SummaryLineage("s1"))
    restated = restate([frozen], FACTS[:1])
    assert restated[1] is frozen
    assert restated[0].is_summary


async def test_fallback_keeps_the_last_messages_and_restates_missing_facts():
    messages = [
        system("rules", id="s"),
        user("Order TX-991 failed, use 456", id="h1"),
        assistant("ok", id="a1"),
        user("next", id="h2"),
        assistant("done", id="a2"),
    ]
    trimmed, index = await fallback(messages, keep=("messages", 2), counter=COUNTER, facts=missing)
    assert index == 1
    assert [message.id for message in trimmed] == ["s", None, "h2", "a2"]
    assert FALLBACK_NOTICE in trimmed[1].content
    assert "- TX-991" in trimmed[1].content


async def test_fallback_without_missing_facts_starting_on_a_user_turn_adds_nothing():
    messages = [user("TX-991 and 456", id="h1"), assistant("a", id="a1")]
    trimmed, index = await fallback(messages, keep=("messages", 2), counter=COUNTER, facts=missing)
    assert index is None
    assert trimmed == messages


async def test_fallback_never_starts_on_an_orphaned_tool_result():
    messages = [user("TX-991 456", id="h0"), *tool_turn(1), assistant("answer", id="x")]
    trimmed, index = await fallback(messages, keep=("messages", 2), counter=COUNTER, facts=missing)
    assert orphaned_tool_results(trimmed) == ()
    assert index == 0
    assert FALLBACK_NOTICE in trimmed[0].content
    assert f"{REQUEST_HEADING}\nTX-991 456" in trimmed[0].content


async def test_fallback_without_any_user_request_only_adds_the_notice():
    messages = [system("rules", id="s"), *tool_turn(1), assistant("x", id="x")]
    trimmed, index = await fallback(
        messages, keep=("messages", 1), counter=COUNTER, facts=lambda _window: ()
    )
    assert index == 1
    assert [message.id for message in trimmed] == ["s", None, "x"]
    assert trimmed[1].content == FALLBACK_NOTICE


async def test_fallback_ignores_summaries_when_looking_for_the_request():
    messages = [summary("old summary"), *tool_turn(1), assistant("x", id="x")]
    trimmed, _ = await fallback(
        messages, keep=("messages", 1), counter=COUNTER, facts=lambda _window: ()
    )
    assert trimmed[0].content == FALLBACK_NOTICE


async def test_fallback_keeps_the_trailing_tool_exchange_whole():
    messages = [system("rules", id="s"), user("TX-991 456", id="h0"), *tool_turn(1)]
    trimmed, _ = await fallback(messages, keep=("messages", 1), counter=COUNTER, facts=missing)
    assert [message.id for message in trimmed][-2:] == ["a1", "t1"]
    assert trimmed[0].role == "system"
    assert orphaned_tool_results(trimmed) == ()


async def test_fallback_by_tokens():
    messages = [user(f"message {index} TX-991 456", id=f"h{index}") for index in range(10)]
    by_tokens, _ = await fallback(messages, keep=("tokens", 40), counter=COUNTER, facts=missing)
    assert 0 < len(by_tokens) < len(messages)
    assert await COUNTER.count(by_tokens) <= 40


def test_summary_identity_and_lineage():
    summary_id = new_summary_id()
    assert summary_id.startswith("contextsage-summary-")
    assert new_summary_id() != summary_id
    stamped = summary("summary", summary_id, generation=3, source_summary_ids=("old",), facts=FACTS)
    assert stamped.id == summary_id
    assert stamped.role == "user"
    assert stamped.lineage == SummaryLineage(summary_id, 3, ("old",), FACTS)
    assert stamped.lineage is not None
    assert stamped.lineage.to_dict() == {
        "summary_id": summary_id,
        "generation": 3,
        "source_summary_ids": ["old"],
        "facts": [
            {"statement": "TX-991", "required": ["TX-991"]},
            {"statement": "User correction: use 456", "required": ["456"]},
        ],
    }
    assert carried_facts([user("x", id="h"), stamped]) == FACTS


def test_lineage_round_trips_through_a_dictionary():
    lineage = SummaryLineage("s1", 2, ("s0",), FACTS)
    assert SummaryLineage.from_dict(lineage.to_dict(), summary_id="other") == lineage


def test_malformed_lineage_records_fall_back_to_a_first_summary():
    valid = {"statement": 'User instruction: "Never refund"', "required": ["Never"]}
    records = [
        valid,
        "not a mapping",
        {"statement": 7, "required": ["x"]},
        {"statement": "x", "required": "x"},
        {"statement": "x", "required": []},
        {"statement": "x", "required": ["x", " "]},
    ]
    lineage = SummaryLineage.from_dict(
        {"summary_id": "", "generation": True, "source_summary_ids": ["a", 1], "facts": records},
        summary_id="s9",
    )
    assert lineage == SummaryLineage(
        "s9", 1, ("a",), (Fact('User instruction: "Never refund"', ("Never",)),)
    )
    assert SummaryLineage.from_dict(1, summary_id="s9") == SummaryLineage("s9")
    assert SummaryLineage.from_dict(
        {"generation": 0, "source_summary_ids": "s0", "facts": "x"}, summary_id="s9"
    ) == SummaryLineage("s9")


def test_carried_facts_skip_facts_their_statement_does_not_satisfy():
    broken = summary("s", facts=(Fact("ORD-12", ("ORD-1",)), FACTS[0]))
    assert carried_facts([broken]) == (FACTS[0],)


def test_replaced_summaries():
    first = summary("one", "s1", generation=2)
    unnamed = Message("user", "two", id="s2", lineage=SummaryLineage(""))
    history = [first, unnamed, user("x", id="h")]
    assert replaced_summaries(history, {"h"}) == (3, ("s1",))
    assert replaced_summaries(history, {"s1", "s2", "h"}) == (1, ())
