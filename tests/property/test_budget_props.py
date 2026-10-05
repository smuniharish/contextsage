from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from contextsage._pipeline.budget import Budget, Trigger


@st.composite
def budgets(draw: st.DrawFn) -> Budget:
    """Valid budgets: the reservations always leave room for input."""
    maximum = draw(st.integers(min_value=1_000, max_value=2_000_000))
    margin = draw(st.floats(min_value=0, max_value=0.5))
    room = maximum - round(maximum * margin) - 1
    return Budget(
        maximum_context_tokens=maximum,
        reserved_output_tokens=draw(st.integers(min_value=0, max_value=room // 2)),
        safety_margin=margin,
        summarization_overhead_tokens=draw(
            st.integers(min_value=0, max_value=room // 2)
        ),
    )


TOKENS = st.integers(min_value=0, max_value=3_000_000)
MESSAGES = st.integers(min_value=0, max_value=500)
CONDITIONS = st.one_of(
    st.tuples(st.just("tokens"), st.integers(min_value=1, max_value=2_000_000)),
    st.tuples(st.just("messages"), st.integers(min_value=1, max_value=400)),
    st.tuples(st.just("fraction"), st.floats(min_value=0.01, max_value=1.0)),
)
CLAUSES = st.lists(CONDITIONS, min_size=1, max_size=3, unique_by=lambda c: c[0]).map(
    dict
)


@given(budgets())
def test_budget_arithmetic(budget):
    assert budget.available_tokens > 0
    assert budget.available_tokens == (
        budget.maximum_context_tokens
        - budget.reserved_output_tokens
        - budget.safety_margin_tokens
        - budget.summarization_overhead_tokens
    )


@given(budgets(), TOKENS, MESSAGES)
def test_budget_mode_fires_exactly_on_overflow(budget, tokens, messages):
    decision = Trigger(None, budget).evaluate(tokens=tokens, messages=messages)
    if tokens > budget.available_tokens:
        assert decision is not None
        assert decision.overflow_tokens == tokens - budget.available_tokens
    else:
        assert decision is None


@given(budgets(), st.integers(min_value=1, max_value=10**6), TOKENS, TOKENS)
def test_token_triggers_are_monotonic(budget, threshold, first, second):
    trigger = Trigger(("tokens", threshold), budget)
    low, high = sorted((first, second))
    if trigger.evaluate(tokens=low, messages=1) is not None:
        assert trigger.evaluate(tokens=high, messages=1) is not None


@given(
    budgets(),
    st.lists(st.one_of(CONDITIONS, CLAUSES), min_size=1, max_size=4),
    TOKENS,
    MESSAGES,
)
def test_lists_are_or_and_clauses_are_and(budget, spec, tokens, messages):
    combined = Trigger(spec, budget).evaluate(tokens=tokens, messages=messages)
    items = [
        Trigger(item, budget).evaluate(tokens=tokens, messages=messages)
        for item in spec
    ]
    assert (combined is not None) == any(item is not None for item in items)
    for item in spec:
        if isinstance(item, dict):
            parts = [
                Trigger((kind, value), budget).evaluate(
                    tokens=tokens, messages=messages
                )
                for kind, value in item.items()
            ]
            whole = Trigger(item, budget).evaluate(tokens=tokens, messages=messages)
            assert (whole is not None) == all(part is not None for part in parts)
    if combined is not None:
        assert combined.overflow_tokens >= 0
