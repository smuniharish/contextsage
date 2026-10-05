from __future__ import annotations

import json

from langchain_core.messages import AIMessage, ToolMessage

from contextsage._pipeline.lineage import summary_message
from contextsage._pipeline.relationships import MAX_DISTINCT_VALUES, find_contradictions
from tests.support.builders import units


def tool(content: str, index: int) -> ToolMessage:
    return ToolMessage(content, tool_call_id=f"c{index}", id=f"t{index}")


def test_conflicting_values_from_different_messages():
    (contradiction,) = find_contradictions(
        units([tool("status=SUCCESS", 0), tool("status: failed", 1)])
    )
    assert contradiction.key == "status"
    assert (contradiction.value_a, contradiction.value_b) == ("SUCCESS", "failed")
    assert (contradiction.unit_a, contradiction.unit_b) == ("t0:0", "t1:0")


def test_values_compare_case_insensitively():
    assert (
        find_contradictions(units([tool("status=OK", 0), tool("status=ok", 1)])) == ()
    )


def test_values_within_one_message_do_not_conflict():
    assert find_contradictions(units([tool("status=SUCCESS\nstatus=FAILED", 0)])) == ()


def test_json_scalar_fields_are_assertions():
    first = json.dumps({"region": "us-east-1", "healthy": True, "replicas": 3})
    second = json.dumps({"region": "eu-west-1", "healthy": False, "notes": ["x"]})
    found = {
        (c.key, c.value_a, c.value_b)
        for c in find_contradictions(units([tool(first, 0), tool(second, 1)]))
    }
    assert found == {("region", "us-east-1", "eu-west-1"), ("healthy", "true", "false")}


def test_volatile_keys_are_ignored():
    messages = [
        tool(
            f"request_id=req-{i} latency: {i}ms elapsed={i} count={i} time=10:00:0{i}",
            i,
        )
        for i in range(4)
    ]
    assert find_contradictions(units(messages)) == ()


def test_keys_with_many_values_are_measurements():
    messages = [tool(f"queue_depth={i}", i) for i in range(MAX_DISTINCT_VALUES + 1)]
    assert find_contradictions(units(messages)) == ()


def test_contradictions_are_bounded_per_key():
    messages = [tool(f"state={value}", i) for i, value in enumerate(("a", "b", "c"))]
    assert len(find_contradictions(units(messages))) == 3


def test_urls_timestamps_and_code_are_not_assertions():
    messages = [
        tool("see http://example.com and 2024-01-01T10:00:00", 0),
        tool("see https://example.org", 1),
        AIMessage("```python\nmode = 1\n```", id="a0"),
        AIMessage("```python\nmode = 2\n```", id="a1"),
    ]
    assert find_contradictions(units(messages)) == ()


def test_long_json_strings_and_nested_values_are_skipped():
    first = json.dumps({"summary": "x" * 50, "nested": {"a": 1}})
    second = json.dumps({"summary": "y" * 50, "nested": {"a": 2}})
    assert find_contradictions(units([tool(first, 0), tool(second, 1)])) == ()


def test_json_values_must_appear_verbatim_in_the_text():
    first = '{"city": "caf\\u00e9", "ratio": 1e5, "state": "open"}'
    second = '{"city": "paris", "ratio": 2.50, "state": "closed"}'
    found = [
        (c.key, c.value_a, c.value_b)
        for c in find_contradictions(units([tool(first, 0), tool(second, 1)]))
    ]
    assert found == [("state", "open", "closed")]


def test_only_prose_and_json_outside_summaries_make_claims():
    messages = [
        tool("2026-10-04T10:00:00Z INFO job state=running\n", 0),
        tool("2026-10-04T10:05:00Z INFO job state=done\n", 1),
        tool("Traceback (most recent call last):\nValueError: bad value\n", 2),
        tool("Traceback (most recent call last):\nValueError: other value\n", 3),
        summary_message("Earlier, the job reported state: pending."),
        tool("The job reports state: queued.", 4),
    ]
    assert find_contradictions(units(messages)) == ()


def test_log_record_fields_are_not_claims():
    first = json.dumps({"level": "info", "msg": "started", "logger": "app"})
    second = json.dumps({"level": "error", "msg": "failed", "logger": "db"})
    assert find_contradictions(units([tool(first, 0), tool(second, 1)])) == ()


def test_json_arrays_have_no_assertions():
    assert find_contradictions(units([tool("[1, 2]", 0), tool("[3]", 1)])) == ()
