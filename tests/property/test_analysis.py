from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from hypothesis import given, settings
from hypothesis import strategies as st
from parsefabric.execution import AsyncExecutionBackend

from contextsage import (
    BalancedPolicy,
    ContextSummarizer,
    MaximumCompressionPolicy,
    MaximumPreservationPolicy,
    ParsingOptions,
    TokenizerTokenCounter,
)
from contextsage._pipeline.models import Preservation
from contextsage._pipeline.preservation import classify
from contextsage._pipeline.recovery import fallback, restate
from contextsage._pipeline.relationships import MAX_DISTINCT_VALUES, find_contradictions
from contextsage._pipeline.validation import orphaned_tool_results, validate
from tests.property.strategies import SENTENCES, conversations, documents
from tests.support.builders import FailingModel, FakeModel, pipeline, tool, user

if TYPE_CHECKING:
    from parsefabric import LanguageModel

    from contextsage import Message, PreservationPolicy
    from contextsage._pipeline.models import Analysis
    from contextsage._pipeline.pipeline import Pipeline
    from contextsage.engine import ContextSize

POLICIES = (MaximumPreservationPolicy(), BalancedPolicy(), MaximumCompressionPolicy())
PIPELINES: dict[PreservationPolicy, Pipeline] = {
    policy: asyncio.run(pipeline(policy)) for policy in POLICIES
}
BALANCED = POLICIES[1]
COUNTER = TokenizerTokenCounter()


def analyze(messages: list[Message], policy: PreservationPolicy = BALANCED) -> Analysis:
    return asyncio.run(PIPELINES[policy].prepare(messages)).analysis


def rewrite(
    model: LanguageModel, messages: list[Message], *, threshold: int, keep: ContextSize
) -> tuple[Message, ...] | None:
    async def run() -> tuple[Message, ...] | None:
        parsing = ParsingOptions(code_detector=None, backend=AsyncExecutionBackend())
        async with ContextSummarizer(
            model, trigger=("tokens", threshold), keep=keep, parsing=parsing
        ) as summarizer:
            result = await summarizer.summarize(messages, thread_id="property")
        return None if result is None else result.messages

    return asyncio.run(run())


def assert_valid(history: tuple[Message, ...] | list[Message]) -> None:
    assert orphaned_tool_results(history) == ()
    conversation = [message for message in history if message.role != "system"]
    assert conversation[0].role == "user"


@given(conversations())
def test_importance_is_bounded_and_facts_contain_what_they_require(messages):
    analysis = analyze(messages)
    assert all(0.0 <= item.value <= 1.0 for item in analysis.importance.values())
    statements = [fact.statement for fact in analysis.facts]
    assert len(statements) == len(set(statements))
    for fact in analysis.facts:
        assert fact.required
        assert all(part.casefold() in fact.statement.casefold() for part in fact.required)


@given(conversations(), st.sampled_from(POLICIES))
def test_every_fact_is_present_before_and_after_compaction(messages, policy):
    prepared = asyncio.run(PIPELINES[policy].prepare(messages))
    facts = prepared.analysis.facts
    assert validate(messages, facts).missing == ()
    assert validate(prepared.messages, facts).missing == ()


@given(conversations())
def test_policies_are_ordered(messages):
    analysis = analyze(messages)
    levels = [classify(analysis.units, analysis.importance, (), policy) for policy in POLICIES]

    def kept(index: int, accepted: set[Preservation]) -> set[str]:
        return {unit_id for unit_id, level in levels[index].items() if level in accepted}

    for accepted in ({Preservation.MUST}, {Preservation.MUST, Preservation.SHOULD}):
        assert kept(0, accepted) >= kept(1, accepted) >= kept(2, accepted)


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
        tool(" ".join(f"{key}={value}" for key, value in pairs), call=f"c{i}", id=f"t{i}")
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
    summary = [user("Unrelated summary.")]
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
    window, index = asyncio.run(
        fallback(
            messages,
            keep=keep,
            counter=COUNTER,
            facts=lambda candidate: validate(candidate, facts).missing,
        )
    )
    assert_valid(window)
    if messages[0].role == "system":
        assert window[0] is messages[0]
    assert validate(window, facts).missing == ()
    assert index is None or window[index].is_summary
    tail = [
        messages.index(message)
        for message in window
        if message.id is not None and message.role != "system"
    ]
    assert tail == list(range(len(messages) - len(tail), len(messages)))


@settings(max_examples=25, deadline=None)
@given(
    conversations(),
    st.integers(min_value=1, max_value=600),
    st.integers(min_value=1, max_value=5),
)
def test_summarizer_always_returns_a_valid_history(messages, threshold, keep):
    rewritten = rewrite(FakeModel(), messages, threshold=threshold, keep=("messages", keep))
    if rewritten is not None:
        assert_valid(rewritten)


@settings(max_examples=15, deadline=None)
@given(conversations(), st.integers(min_value=1, max_value=4))
def test_failing_summary_models_never_break_the_agent(messages, keep):
    rewritten = rewrite(FailingModel(), messages, threshold=1, keep=("messages", keep))
    if rewritten is not None:
        assert_valid(rewritten)


@given(SENTENCES, documents())
def test_analysis_is_deterministic(question, text):
    messages = [user(question, id="h"), tool(text, call="c", id="t")]
    first, second = analyze(messages), analyze(messages)
    assert first.units == second.units
    assert first.facts == second.facts
    assert dict(first.preservation) == dict(second.preservation)
    assert dict(first.importance) == dict(second.importance)
