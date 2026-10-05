from __future__ import annotations

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.messages.utils import count_tokens_approximately

from contextsage._pipeline.lineage import (
    METADATA_KEY,
    carried_facts,
    generation_of,
    is_summary,
    new_summary_id,
    replaced_summaries,
    stamp,
    summary_message,
)
from contextsage._pipeline.models import Fact
from contextsage._pipeline.recovery import (
    FACTS_HEADING,
    FALLBACK_NOTICE,
    REQUEST_HEADING,
    facts_block,
    fallback,
    restate,
)
from contextsage._pipeline.validation import orphaned_tool_results, validate

FACTS = (Fact("TX-991", ("TX-991",)), Fact("User correction: use 456", ("456",)))


def missing(window):
    return validate(window, FACTS).missing


def tool_turn(index: int) -> list:
    return [
        AIMessage(
            "",
            id=f"a{index}",
            tool_calls=[{"id": f"c{index}", "name": "t", "args": {}}],
        ),
        ToolMessage(f"result {index}", tool_call_id=f"c{index}", id=f"t{index}"),
    ]


def test_facts_block():
    assert (
        facts_block(FACTS) == f"{FACTS_HEADING}\n- TX-991\n- User correction: use 456"
    )


def test_facts_block_states_each_fact_once():
    identifier = Fact("customer 456", ("customer 456",))
    correction = Fact('User correction: "use customer 456 instead"', ("456",))
    longer, shorter = Fact("ORD-12", ("ORD-12",)), Fact("ORD-1", ("ORD-1",))
    assert facts_block((identifier, correction, longer, shorter)) == (
        f"{FACTS_HEADING}\n"
        '- User correction: "use customer 456 instead"\n'
        "- ORD-12\n"
        "- ORD-1"
    )


def test_restate_appends_to_the_summary_message():
    summary = stamp(
        summary_message("Here is a summary."),
        summary_id="s1",
        generation=1,
        source_summary_ids=(),
        facts=FACTS,
    )
    messages = [summary, HumanMessage("next", id="h")]
    restated = restate(messages, FACTS[:1])
    assert restated[0].content == f"Here is a summary.\n\n{FACTS_HEADING}\n- TX-991"
    assert restated[0].id == "s1"
    assert restated[1] is messages[1]


def test_restate_inserts_a_summary_after_system_messages():
    messages = [SystemMessage("rules", id="s"), HumanMessage("next", id="h")]
    restated = restate(messages, FACTS[:1])
    assert [message.type for message in restated] == ["system", "human", "human"]
    assert is_summary(restated[1])


def test_fallback_keeps_the_last_messages_and_restates_missing_facts():
    messages = [
        SystemMessage("rules", id="s"),
        HumanMessage("Order TX-991 failed, use 456", id="h1"),
        AIMessage("ok", id="a1"),
        HumanMessage("next", id="h2"),
        AIMessage("done", id="a2"),
    ]
    trimmed, index = fallback(
        messages,
        keep=("messages", 2),
        token_counter=count_tokens_approximately,
        facts=missing,
    )
    assert index == 1
    assert [message.id for message in trimmed] == ["s", None, "h2", "a2"]
    assert FALLBACK_NOTICE in trimmed[1].text
    assert "- TX-991" in trimmed[1].text


def test_fallback_without_missing_facts_starting_on_a_user_turn_adds_nothing():
    messages = [HumanMessage("TX-991 and 456", id="h1"), AIMessage("a", id="a1")]
    trimmed, index = fallback(
        messages,
        keep=("messages", 2),
        token_counter=count_tokens_approximately,
        facts=missing,
    )
    assert index is None
    assert trimmed == messages


def test_fallback_never_starts_on_an_orphaned_tool_result():
    messages = [
        HumanMessage("TX-991 456", id="h0"),
        *tool_turn(1),
        AIMessage("answer", id="x"),
    ]
    trimmed, index = fallback(
        messages,
        keep=("messages", 2),
        token_counter=count_tokens_approximately,
        facts=missing,
    )
    assert orphaned_tool_results(trimmed) == ()
    assert trimmed[index or 0].type == "human"
    assert FALLBACK_NOTICE in trimmed[0].text
    assert f"{REQUEST_HEADING}\nTX-991 456" in trimmed[0].text


def test_fallback_without_any_user_request_only_adds_the_notice():
    messages = [SystemMessage("rules", id="s"), *tool_turn(1), AIMessage("x", id="x")]
    trimmed, index = fallback(
        messages,
        keep=("messages", 1),
        token_counter=count_tokens_approximately,
        facts=lambda _window: (),
    )
    assert index == 1
    assert [message.id for message in trimmed] == ["s", None, "x"]
    assert trimmed[1].text == FALLBACK_NOTICE


def test_fallback_keeps_the_trailing_tool_exchange_whole():
    messages = [
        SystemMessage("rules", id="s"),
        HumanMessage("TX-991 456", id="h0"),
        *tool_turn(1),
    ]
    trimmed, _ = fallback(
        messages,
        keep=("messages", 1),
        token_counter=count_tokens_approximately,
        facts=missing,
    )
    assert [message.id for message in trimmed][-2:] == ["a1", "t1"]
    assert trimmed[0].type == "system"
    assert orphaned_tool_results(trimmed) == ()


def test_fallback_by_tokens_and_fraction():
    messages = [
        HumanMessage(f"message {index} TX-991 456", id=f"h{index}")
        for index in range(10)
    ]
    by_tokens, _ = fallback(
        messages,
        keep=("tokens", 40),
        token_counter=count_tokens_approximately,
        facts=missing,
    )
    assert 0 < len(by_tokens) < len(messages)
    assert sum(count_tokens_approximately([m]) for m in by_tokens[1:]) <= 40


def test_summary_identity_and_lineage():
    summary_id = new_summary_id()
    assert summary_id.startswith("contextsage-summary-")
    assert new_summary_id() != summary_id
    stamped = stamp(
        HumanMessage(
            "summary", additional_kwargs={"lc_source": "summarization", "x": 1}
        ),
        summary_id=summary_id,
        generation=3,
        source_summary_ids=("old",),
        facts=FACTS,
    )
    assert stamped.id == summary_id
    assert stamped.additional_kwargs["x"] == 1
    assert stamped.additional_kwargs[METADATA_KEY] == {
        "summary_id": summary_id,
        "generation": 3,
        "source_summary_ids": ["old"],
        "facts": [
            {"statement": "TX-991", "required": ["TX-991"]},
            {"statement": "User correction: use 456", "required": ["456"]},
        ],
    }
    assert generation_of(stamped) == 3
    assert carried_facts([HumanMessage("x", id="h"), stamped]) == FACTS


def test_malformed_fact_records_are_skipped():
    valid = {"statement": 'User instruction: "Never refund"', "required": ["Never"]}
    records = [
        valid,
        "not a mapping",
        {"statement": 7, "required": ["x"]},
        {"statement": "x", "required": "x"},
        {"statement": "x", "required": []},
        {"statement": "x", "required": ["x", " "]},
        {"statement": "ORD-12", "required": ["ORD-1"]},
    ]
    summary = HumanMessage(
        "s",
        additional_kwargs={
            "lc_source": "summarization",
            METADATA_KEY: {"facts": records},
        },
    )
    unrecorded = [
        summary_message("LangChain summary"),
        HumanMessage(
            "s", additional_kwargs={"lc_source": "summarization", METADATA_KEY: 1}
        ),
        HumanMessage("s", additional_kwargs={METADATA_KEY: {"facts": [valid]}}),
    ]
    assert carried_facts([*unrecorded, summary]) == (
        Fact('User instruction: "Never refund"', ("Never",)),
    )


def test_summaries_without_a_lineage_record_are_generation_one():
    assert generation_of(summary_message("LangChain summary")) == 1
    broken = HumanMessage(
        "s",
        additional_kwargs={
            "lc_source": "summarization",
            METADATA_KEY: {"generation": 0},
        },
    )
    assert generation_of(broken) == 1
    assert not is_summary(
        AIMessage("s", additional_kwargs={"lc_source": "summarization"})
    )


def test_replaced_summaries():
    first = stamp(
        summary_message("one"),
        summary_id="s1",
        generation=2,
        source_summary_ids=(),
        facts=(),
    )
    langchain = summary_message("two").model_copy(update={"id": "s2"})
    history = [first, langchain, HumanMessage("x", id="h")]
    assert replaced_summaries(history, {"h"}) == (3, ("s1", "s2"))
    assert replaced_summaries(history, {"s1", "s2", "h"}) == (1, ())
