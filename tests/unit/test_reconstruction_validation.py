from __future__ import annotations

from contextsage import Fact
from contextsage._pipeline.reconstruction import rebuild
from contextsage._pipeline.validation import (
    ValidationResult,
    canonical,
    contains,
    orphaned_tool_results,
    validate,
)
from tests.support.builders import assistant, tool, units, user


async def test_rebuild_without_replacements_returns_the_same_messages():
    messages = [user("a", id="h")]
    rebuilt = rebuild(messages, await units(messages), {})
    assert rebuilt == messages
    assert rebuilt[0] is messages[0]


async def test_rebuild_replaces_only_the_compacted_span():
    text = "Heading line\nINFO a\nINFO b\nTrailing prose\n"
    messages = [tool(text, call="c", id="t"), user("x", id="h")]
    decomposed = await units(messages)
    log = next(unit for unit in decomposed if unit.kind == "log")
    rebuilt = rebuild(messages, decomposed, {log.unit_id: "[logs]\n"})
    rewritten = rebuilt[0]
    assert rewritten.role == "tool"
    assert rewritten.content == "Heading line\n[logs]\nTrailing prose\n"
    assert rewritten.tool_call_id == "c"
    assert rewritten.id == "t"
    assert rebuilt[1] is messages[1]


def test_validate_matches_facts_case_insensitively():
    messages = [user("Customer 456 confirmed; status success.", id="h")]
    facts = (
        Fact("customer 456", ("customer 456",)),
        Fact("status", ("SUCCESS", "failed")),
    )
    result = validate(messages, facts)
    assert result.missing == (facts[1],)
    assert result.orphaned_tool_results == ()


def test_validate_passes_when_everything_survives():
    result = validate([user("TX-991", id="h")], (Fact("TX-991", ("TX-991",)),))
    assert result == ValidationResult((), ())


def test_validate_ignores_whitespace_and_apostrophe_style():
    fact = Fact("instruction", ("Don't deploy on Fridays.",))
    messages = [user("Don\u2019t  deploy\non   Fridays.", id="h")]
    assert validate(messages, (fact,)).missing == ()


def test_validate_matches_whole_tokens_within_one_message():
    order = Fact("ORD-1", ("ORD-1",))
    phrase = Fact("phrase", ("order ORD-12",))
    messages = [user("order", id="h1"), user("ORD-12 xORD-1", id="h2")]
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
        assistant(id="a", calls=("c1",)),
        tool("ok", call="c1", id="t1"),
        tool("lost", call="c2", id="t2"),
    ]
    assert orphaned_tool_results(messages) == ("c2",)
    assert validate(messages, ()).orphaned_tool_results == ("c2",)
