"""Hypothesis strategies for agent context."""

from __future__ import annotations

import json

from hypothesis import strategies as st
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

WORDS = st.sampled_from(
    [
        "payment",
        "failed",
        "customer",
        "456",
        "TX-991",
        "ok",
        "must",
        "never",
        "instead",
        "of",
        "use",
        "No,",
        "status=ok",
        "status=failed",
        "request_id=r-1",
        "timeout",
        "the",
        "queue",
        "decision",
        "INC-9931",
    ]
)
SENTENCES = st.lists(WORDS, min_size=1, max_size=12).map(" ".join)
LEVELS = st.sampled_from(["DEBUG", "INFO", "WARN", "ERROR", "CRITICAL", "info"])

JSON_VALUES = st.recursive(
    st.none()
    | st.booleans()
    | st.integers(min_value=-(10**6), max_value=10**6)
    | st.floats(allow_nan=False, allow_infinity=False, width=32)
    | st.text(max_size=8),
    lambda children: (
        st.lists(children, max_size=8)
        | st.dictionaries(
            st.text(max_size=6).filter(lambda key: not key.startswith("__")),
            children,
            max_size=5,
        )
    ),
    max_leaves=25,
)


@st.composite
def log_lines(draw: st.DrawFn) -> str:
    second = draw(st.integers(min_value=0, max_value=59))
    level = draw(LEVELS)
    return f"2024-08-01T03:00:{second:02d} {level} {draw(SENTENCES)}"


LINES = st.one_of(
    SENTENCES,
    log_lines(),
    st.builds(
        lambda level, text: f"{level} {text}",
        st.sampled_from(["INFO", "ERROR"]),
        SENTENCES,
    ),
    JSON_VALUES.map(json.dumps),
    st.just("Traceback (most recent call last):"),
    st.just('  File "app.py", line 3, in main'),
    st.just("ValueError: bad value"),
    st.just("| a | b |"),
    st.just("|---|---|"),
    st.just("```python"),
    st.just("```"),
    st.just(""),
    st.just("   "),
    st.text(max_size=30),
)
TERMINATORS = st.sampled_from(["\n", "\r\n", "\r", "\u2028", "\x0b"])


@st.composite
def documents(draw: st.DrawFn) -> str:
    """Multi-line agent context mixing logs, JSON, prose and arbitrary text."""
    lines = draw(st.lists(LINES, min_size=1, max_size=25))
    pieces = [line + draw(TERMINATORS) for line in lines[:-1]]
    pieces.append(lines[-1] + draw(st.sampled_from(["", "\n"])))
    return "".join(pieces)


@st.composite
def conversations(draw: st.DrawFn) -> list:
    """Valid histories: optional system prompt, turns and complete tool exchanges."""
    messages: list = []
    if draw(st.booleans()):
        messages.append(SystemMessage(draw(SENTENCES), id="system"))
    turns = draw(st.integers(min_value=1, max_value=8))
    for turn in range(turns):
        messages.append(HumanMessage(draw(documents()), id=f"h{turn}"))
        tools = draw(st.integers(min_value=0, max_value=2))
        if tools:
            calls = [
                {"id": f"c{turn}-{index}", "name": "lookup", "args": {}}
                for index in range(tools)
            ]
            messages.append(AIMessage("", id=f"call{turn}", tool_calls=calls))
            messages.extend(
                ToolMessage(
                    draw(documents()), tool_call_id=call["id"], id=f"t{call['id']}"
                )
                for call in calls
            )
        if draw(st.booleans()) or turn < turns - 1:
            messages.append(AIMessage(draw(SENTENCES), id=f"a{turn}"))
    return messages
