from __future__ import annotations

import json
import re

import pytest
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from contextsage._pipeline import transformation
from contextsage._pipeline.models import Kind, ParsedJSON, Preservation, Unit
from contextsage._pipeline.signals import (
    DEFAULT_IDENTIFIER_PATTERNS,
    find_identifiers,
)
from contextsage._pipeline.transformation import (
    collapse_repeats,
    compact,
    compact_json,
    plan,
)
from tests.support.builders import heartbeat_log, units


def log_unit(
    text: str,
    severities: tuple[str | None, ...] | None = None,
    kind: str = Kind.LOG,
    patterns: tuple[re.Pattern[str], ...] = DEFAULT_IDENTIFIER_PATTERNS,
) -> Unit:
    lines = text.splitlines(keepends=True)
    identifiers, identifier_lines = find_identifiers(text, patterns)
    return Unit(
        unit_id="u",
        message_index=0,
        role="tool",
        kind=kind,
        text=text,
        first_line=10,
        line_severities=severities or tuple("INFO" for _ in lines),
        identifiers=identifiers,
        identifier_lines=identifier_lines,
    )


def test_collapse_keeps_run_ends_and_reports_the_omitted_range():
    text = heartbeat_log(50)
    compacted = collapse_repeats(log_unit(text))
    lines = compacted.splitlines(keepends=True)
    original = text.splitlines(keepends=True)
    assert lines == [
        original[0],
        "... 48 similar lines omitted (lines 11-58) ...\n",
        original[-1],
    ]


def test_short_runs_and_identifier_lines_are_kept():
    text = "INFO ok\nINFO ok\n" + "".join(
        f"INFO request_id=req-{index} done\n" for index in range(5)
    )
    assert collapse_repeats(log_unit(text)) == text


def test_runs_shorter_than_the_marker_are_kept():
    text = "a 1\na 2\na 3\n"
    assert collapse_repeats(log_unit(text)) == text


def test_warnings_keep_distinct_numbers():
    text = "".join(
        f"WARN slow query took {index}00 ms on shard 7\n" for index in range(1, 6)
    )
    severities = tuple("WARNING" for _ in range(5))
    assert collapse_repeats(log_unit(text, severities)) == text


def test_table_rows_collapse_only_when_identical():
    rows = "| sku | qty |\n|---|---|\n" + "| A-1 | 1 |\n" * 6 + "| B-2 | 3 |\n" * 2
    compacted = collapse_repeats(log_unit(rows, kind=Kind.TABLE))
    assert compacted == (
        "| sku | qty |\n|---|---|\n| A-1 | 1 |\n"
        "... 4 similar lines omitted (lines 13-16) ...\n"
        "| A-1 | 1 |\n| B-2 | 3 |\n| B-2 | 3 |\n"
    )


def test_marker_reuses_the_line_terminator():
    text = "".join(f"2024-01-01T00:00:{index:02d} INFO tick\r\n" for index in range(6))
    compacted = collapse_repeats(log_unit(text))
    assert "omitted (lines 11-14) ...\r\n" in compacted


def test_marker_terminator_defaults_to_newline():
    text = "".join(f"2024-01-01T00:00:{index:02d} INFO tick\n" for index in range(5))
    text = text.rstrip("\n")
    compacted = collapse_repeats(log_unit(text))
    assert compacted.endswith("INFO tick")


DOCUMENT = {
    "items": [{"sku": "A-1"}] * 3 + [{"sku": "B-2"}] + [{"sku": "A-1"}] * 2,
    "tags": ["x", "y"],
}


def expand(value: object) -> object:
    """Undo balanced compaction: repeat every collapsed run."""
    if isinstance(value, dict):
        return {key: expand(item) for key, item in value.items()}
    if isinstance(value, list):
        expanded: list[object] = []
        for item in value:
            if isinstance(item, dict) and "__repeated__" in item:
                expanded.extend([expand(item["value"])] * item["__repeated__"])
            else:
                expanded.append(expand(item))
        return expanded
    return value


def test_maximum_preservation_only_minifies():
    assert compact_json(DOCUMENT, "maximum_preservation") == json.dumps(
        DOCUMENT, separators=(",", ":")
    )


def test_balanced_collapses_adjacent_duplicates_losslessly():
    compacted = json.loads(compact_json(DOCUMENT, "balanced"))
    assert compacted["items"] == [
        {"__repeated__": 3, "value": {"sku": "A-1"}},
        {"sku": "B-2"},
        {"sku": "A-1"},
        {"sku": "A-1"},
    ]
    assert expand(compacted) == DOCUMENT


def test_collapsing_never_lengthens_the_document():
    assert compact_json([0, 0, 1, 1, 1], "balanced") == "[0,0,1,1,1]"
    assert compact_json([0, 1, 0], "maximum_compression") == "[0,1,0]"
    assert compact_json(list(range(11)), "maximum_compression") == json.dumps(
        list(range(11)), separators=(",", ":")
    )


def test_maximum_compression_groups_and_samples():
    compacted = json.loads(compact_json(DOCUMENT, "maximum_compression"))
    assert compacted["items"] == [
        {"__repeated__": 5, "value": {"sku": "A-1"}},
        {"sku": "B-2"},
    ]
    long_list = list(range(30))
    sampled = json.loads(compact_json(long_list, "maximum_compression"))
    assert sampled == [0, 1, 2, 3, 4, {"__omitted__": 20}, 25, 26, 27, 28, 29]


def test_non_ascii_text_is_kept_readable():
    assert compact_json({"name": "Zoë"}, "balanced") == '{"name":"Zoë"}'


def test_compact_json_unit_keeps_surrounding_whitespace():
    document = {"items": [1] * 20}
    text = "\n" + json.dumps(document, indent=2) + "\n\n"
    unit = Unit(
        unit_id="u",
        message_index=0,
        role="tool",
        kind=Kind.JSON,
        text=text,
        first_line=1,
        line_severities=(),
        identifiers=(),
        document=ParsedJSON(document),
    )
    compacted = compact(unit, policy="balanced", lossy=True)
    assert compacted == '\n{"items":[{"__repeated__":20,"value":1}]}\n\n'


def test_compact_json_without_a_document_is_skipped():
    unit = log_unit("{}", kind=Kind.JSON)
    assert compact(unit, policy="balanced", lossy=True) is None


def test_compaction_that_does_not_shrink_is_discarded():
    assert compact(log_unit("INFO a\n"), policy="balanced", lossy=True) is None


def test_compaction_failures_keep_the_unit(monkeypatch, caplog):
    def broken(*args: object, **kwargs: object) -> str:
        raise RuntimeError("bug")

    monkeypatch.setattr(transformation, "collapse_repeats", broken)
    unit = log_unit(heartbeat_log(20))
    assert compact(unit, policy="balanced", lossy=True) is None
    assert "could not compact a log unit" in caplog.text


def test_plan_selects_structured_units_in_text_messages():
    messages = [
        SystemMessage("INFO a\nINFO b\nINFO c\n", id="s"),
        ToolMessage(heartbeat_log(5), tool_call_id="c", id="t"),
        HumanMessage([{"type": "text", "text": heartbeat_log(5)}], id="h"),
        ToolMessage("plain prose", tool_call_id="d", id="p"),
        ToolMessage('{"a": [1, 1, 1]}', tool_call_id="e", id="j"),
    ]
    decomposed = units(messages)
    levels = {unit.unit_id: Preservation.COMPRESSIBLE for unit in decomposed}
    assert [
        (unit.unit_id, lossy) for unit, lossy in plan(decomposed, levels, messages)
    ] == [
        ("t:0", True),
        ("j:0", True),
    ]
    levels = {unit.unit_id: Preservation.MUST for unit in decomposed}
    assert [
        (unit.unit_id, lossy) for unit, lossy in plan(decomposed, levels, messages)
    ] == [
        ("j:0", False),
    ]


def test_must_preserve_json_is_only_compacted_losslessly():
    items = [{"sku": "A-1", "qty": 1}] * 30
    unit = Unit(
        unit_id="u",
        message_index=0,
        role="tool",
        kind=Kind.JSON,
        text=json.dumps(items),
        first_line=1,
        line_severities=(None,),
        identifiers=(),
        document=ParsedJSON(items),
    )
    lossless = compact(unit, policy="maximum_compression", lossy=False)
    assert lossless is not None
    assert expand(json.loads(lossless)) == items
    lossy = compact(unit, policy="maximum_compression", lossy=True)
    assert lossy == '[{"__repeated__":30,"value":{"sku":"A-1","qty":1}}]'


@pytest.mark.parametrize("pattern", [re.compile(r"worker-\d")])
def test_custom_identifier_patterns_protect_lines(pattern):
    text = heartbeat_log(10)
    assert collapse_repeats(log_unit(text, patterns=(pattern,))) == text
