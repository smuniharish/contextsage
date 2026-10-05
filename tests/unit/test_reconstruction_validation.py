from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from contextsage._pipeline.models import Fact
from contextsage._pipeline.reconstruction import rebuild
from contextsage._pipeline.validation import (
    ValidationResult,
    canonical,
    contains,
    orphaned_tool_results,
    validate,
)
from tests.support.builders import units


def test_rebuild_without_replacements_returns_the_same_messages():
    messages = [HumanMessage("a", id="h")]
    rebuilt = rebuild(messages, units(messages), {})
    assert rebuilt == messages
    assert rebuilt[0] is messages[0]


def test_rebuild_replaces_only_the_compacted_span():
    text = "Heading line\nINFO a\nINFO b\nTrailing prose\n"
    messages = [ToolMessage(text, tool_call_id="c", id="t"), HumanMessage("x", id="h")]
    decomposed = units(messages)
    log = next(unit for unit in decomposed if unit.kind == "log")
    rebuilt = rebuild(messages, decomposed, {log.unit_id: "[logs]\n"})
    tool = rebuilt[0]
    assert isinstance(tool, ToolMessage)
    assert tool.content == "Heading line\n[logs]\nTrailing prose\n"
    assert tool.tool_call_id == "c"
    assert tool.id == "t"
    assert rebuilt[1] is messages[1]


def test_validate_matches_facts_case_insensitively():
    messages = [HumanMessage("Customer 456 confirmed; status success.", id="h")]
    facts = (
        Fact("customer 456", ("customer 456",)),
        Fact("status", ("SUCCESS", "failed")),
    )
    result = validate(messages, facts)
    assert result.missing == (facts[1],)
    assert result.orphaned_tool_results == ()


def test_validate_passes_when_everything_survives():
    result = validate([HumanMessage("TX-991", id="h")], (Fact("TX-991", ("TX-991",)),))
    assert result == ValidationResult((), ())


def test_validate_ignores_whitespace_and_apostrophe_style():
    fact = Fact("instruction", ("Don't deploy on Fridays.",))
    messages = [HumanMessage("Don\u2019t  deploy\non   Fridays.", id="h")]
    assert validate(messages, (fact,)).missing == ()


def test_validate_matches_whole_tokens_within_one_message():
    order = Fact("ORD-1", ("ORD-1",))
    phrase = Fact("phrase", ("order ORD-12",))
    messages = [HumanMessage("order", id="h1"), HumanMessage("ORD-12 xORD-1", id="h2")]
    assert validate(messages, (order, phrase)).missing == (order, phrase)


def test_contains_requires_token_boundaries():
    assert contains("ord-12 ord-1", "ord-1")
    assert contains("(ord-1)", "ord-1")
    assert not contains("ord-1_x", "ord-1")
    assert contains("anything", "")


def test_canonical_form():
    assert canonical("  Don\u2019t\tSHIP\n now ") == "don't ship now"


def test_orphaned_tool_results_are_reported():
    messages = [
        AIMessage("", id="a", tool_calls=[{"id": "c1", "name": "t", "args": {}}]),
        ToolMessage("ok", tool_call_id="c1", id="t1"),
        ToolMessage("lost", tool_call_id="c2", id="t2"),
    ]
    assert orphaned_tool_results(messages) == ("c2",)
    assert validate(messages, ()).orphaned_tool_results == ("c2",)
