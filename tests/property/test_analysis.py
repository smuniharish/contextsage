from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from hypothesis import given, settings
from hypothesis import strategies as st
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages.utils import count_tokens_approximately
from langgraph.runtime import Runtime

from contextsage import IntelligentSummarizationMiddleware
from contextsage._pipeline.models import Preservation
from contextsage._pipeline.preservation import POLICIES, classify
from contextsage._pipeline.recovery import fallback, restate
from contextsage._pipeline.relationships import MAX_DISTINCT_VALUES, find_contradictions
from contextsage._pipeline.validation import orphaned_tool_results, validate
from tests.property.strategies import SENTENCES, conversations, documents
from tests.support.builders import FailingModel, pipeline, state, summary_model

if TYPE_CHECKING:
    from contextsage._pipeline.models import Analysis
    from contextsage._pipeline.preservation import Policy

PIPELINES = {policy: pipeline(policy) for policy in POLICIES}


def analyze(messages: list, policy: Policy = "balanced") -> Analysis:
    return asyncio.run(PIPELINES[policy].prepare(messages)).analysis


@given(conversations())
def test_importance_is_bounded_and_facts_contain_what_they_require(messages):
    analysis = analyze(messages)
    assert all(0.0 <= item.value <= 1.0 for item in analysis.importance.values())
    statements = [fact.statement for fact in analysis.facts]
    assert len(statements) == len(set(statements))
    for fact in analysis.facts:
        assert fact.required
        assert all(
            part.casefold() in fact.statement.casefold() for part in fact.required
        )


@given(conversations(), st.sampled_from(POLICIES))
def test_every_fact_is_present_before_and_after_compaction(messages, policy):
    prepared = asyncio.run(PIPELINES[policy].prepare(messages))
    facts = prepared.analysis.facts
    assert validate(messages, facts).missing == ()
    assert validate(prepared.messages, facts).missing == ()


@given(conversations())
def test_policies_are_ordered(messages):
    analysis = analyze(messages)
    levels = {
        policy: classify(analysis.units, analysis.importance, (), policy)
        for policy in POLICIES
    }

    def kept(policy: Policy, accepted: set[Preservation]) -> set[str]:
        return {
            unit_id for unit_id, level in levels[policy].items() if level in accepted
        }

    for accepted in ({Preservation.MUST}, {Preservation.MUST, Preservation.SHOULD}):
        assert (
            kept("maximum_preservation", accepted)
            >= kept("balanced", accepted)
            >= kept("maximum_compression", accepted)
        )


@given(
    st.lists(
        st.lists(
            st.tuples(
                st.sampled_from(["status", "region", "mode", "owner", "tier"]),
                st.sampled_from(["a", "b", "c", "d", "e", "f"]),
            ),
            min_size=1,
            max_size=4,
        ),
        min_size=1,
        max_size=8,
    )
)
def test_contradictions_are_bounded_and_cross_message(assertions):
    messages = [
        ToolMessage(
            " ".join(f"{key}={value}" for key, value in pairs),
            tool_call_id=f"c{i}",
            id=f"t{i}",
        )
        for i, pairs in enumerate(assertions)
    ]
    units = analyze(messages).units
    contradictions = find_contradictions(units)
    keys = {contradiction.key for contradiction in contradictions}
    pairs = MAX_DISTINCT_VALUES * (MAX_DISTINCT_VALUES - 1) // 2
    assert len(contradictions) <= pairs * len(keys)
    by_id = {unit.unit_id: unit for unit in units}
    for contradiction in contradictions:
        first, second = by_id[contradiction.unit_a], by_id[contradiction.unit_b]
        assert first.message_index != second.message_index
        assert contradiction.value_a.casefold() != contradiction.value_b.casefold()


@given(conversations())
def test_restating_missing_facts_always_satisfies_validation(messages):
    facts = analyze(messages).facts
    summary = [
        HumanMessage(
            "Unrelated summary.", additional_kwargs={"lc_source": "summarization"}
        )
    ]
    restated = restate(summary, validate(summary, facts).missing)
    assert validate(restated, facts).missing == ()


@given(
    conversations(),
    st.one_of(
        st.tuples(st.just("messages"), st.integers(min_value=1, max_value=6)),
        st.tuples(st.just("tokens"), st.integers(min_value=1, max_value=400)),
    ),
)
def test_fallback_windows_are_always_valid(messages, keep):
    facts = analyze(messages).facts
    window, index = fallback(
        messages,
        keep=keep,
        token_counter=count_tokens_approximately,
        facts=lambda candidate: validate(candidate, facts).missing,
    )
    assert orphaned_tool_results(window) == ()
    conversation = [
        message for message in window if not isinstance(message, SystemMessage)
    ]
    assert conversation[0].type == "human"
    if isinstance(messages[0], SystemMessage):
        assert window[0] is messages[0]
    assert validate(window, facts).missing == ()
    assert (
        index is None or window[index].additional_kwargs["lc_source"] == "summarization"
    )
    tail = [
        messages.index(message)
        for message in window
        if message.id is not None and not isinstance(message, SystemMessage)
    ]
    assert tail == list(range(len(messages) - len(tail), len(messages)))


@settings(max_examples=25)
@given(
    conversations(),
    st.integers(min_value=1, max_value=600),
    st.integers(min_value=1, max_value=5),
)
def test_middleware_always_returns_a_valid_history(messages, threshold, keep):
    middleware = IntelligentSummarizationMiddleware(
        summary_model(),
        trigger=("tokens", threshold),
        keep=("messages", keep),
        code_languages=(),
    )
    update = middleware.before_model(state(messages), Runtime())
    if update is None:
        return
    rewritten = update["messages"][1:]
    assert orphaned_tool_results(rewritten) == ()
    conversation = [m for m in rewritten if not isinstance(m, SystemMessage)]
    assert conversation[0].type == "human"


@settings(max_examples=15)
@given(conversations(), st.integers(min_value=1, max_value=4))
def test_failing_summary_models_never_break_the_agent(messages, keep):
    middleware = IntelligentSummarizationMiddleware(
        FailingModel(),
        trigger=("tokens", 1),
        keep=("messages", keep),
        code_languages=(),
    )
    update = middleware.before_model(state(messages), Runtime())
    if update is None:
        return
    rewritten = update["messages"][1:]
    assert orphaned_tool_results(rewritten) == ()
    conversation = [m for m in rewritten if not isinstance(m, SystemMessage)]
    assert conversation[0].type == "human"


@given(SENTENCES, documents())
def test_analysis_is_deterministic(question, text):
    messages = [
        HumanMessage(question, id="h"),
        ToolMessage(text, tool_call_id="c", id="t"),
    ]
    first, second = analyze(messages), analyze(messages)
    assert first.units == second.units
    assert first.facts == second.facts
    assert dict(first.preservation) == dict(second.preservation)
    assert dict(first.importance) == dict(second.importance)
