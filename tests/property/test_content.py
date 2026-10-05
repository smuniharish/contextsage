from __future__ import annotations

import asyncio
import json
import re

from hypothesis import given, settings
from hypothesis import strategies as st
from langchain_core.messages import HumanMessage, ToolMessage

from contextsage._pipeline.models import Kind, Unit
from contextsage._pipeline.reconstruction import rebuild
from contextsage._pipeline.signals import (
    _HEX_RUN,
    DEFAULT_IDENTIFIER_PATTERNS,
    _mask_hex_id,
    find_identifiers,
)
from contextsage._pipeline.transformation import collapse_repeats, compact_json
from tests.property.strategies import JSON_VALUES, documents
from tests.support.builders import pipeline
from tests.unit.test_transformation import expand

PIPELINE = pipeline()


def decompose(messages: list) -> tuple[Unit, ...]:
    return asyncio.run(PIPELINE.prepare(messages)).analysis.units


@given(st.lists(st.one_of(documents(), st.text(max_size=200)), min_size=1, max_size=4))
def test_units_tile_every_message_exactly(texts):
    messages = [
        ToolMessage(text, tool_call_id=f"c{i}", id=f"t{i}")
        for i, text in enumerate(texts)
    ]
    units = decompose(messages)
    for index, message in enumerate(messages):
        joined = "".join(unit.text for unit in units if unit.message_index == index)
        assert joined == (message.text if message.text.strip() else "")
    for unit in units:
        assert unit.text
        assert unit.first_line >= 1
        assert len(unit.line_severities) == len(unit.text.splitlines(keepends=True))


@given(st.lists(documents(), min_size=1, max_size=3))
def test_rebuilding_without_changes_is_the_identity(texts):
    messages = [HumanMessage(text, id=f"h{i}") for i, text in enumerate(texts)]
    units = decompose(messages)
    same = rebuild(messages, units, {unit.unit_id: unit.text for unit in units})
    assert [message.content for message in same] == [
        message.content for message in messages
    ]


@given(documents())
def test_prepared_history_keeps_every_message_and_its_identity(text):
    messages = [
        HumanMessage("question", id="h"),
        ToolMessage(text, tool_call_id="c", id="t"),
    ]
    prepared = asyncio.run(PIPELINE.prepare(messages))
    assert [message.id for message in prepared.messages] == ["h", "t"]
    tool = prepared.messages[1]
    assert isinstance(tool, ToolMessage)
    assert tool.tool_call_id == "c"
    assert len(tool.text) <= len(text)


LINE_POOL = st.sampled_from(
    [
        "2024-08-01T03:00:01 INFO worker-1 processing queue",
        "2024-08-01T03:00:02 INFO worker-2 processing queue",
        "INFO heartbeat ok",
        "INFO request_id=req-7 done",
        "INFO order ORD-1234 shipped",
        "",
        "INFO cache warm",
    ]
)


@given(st.lists(LINE_POOL, min_size=1, max_size=60))
def test_collapsing_only_drops_runs_of_similar_lines(lines):
    text = "".join(f"{line}\n" for line in lines)
    identifiers, identifier_lines = find_identifiers(text, DEFAULT_IDENTIFIER_PATTERNS)
    unit = Unit(
        unit_id="u",
        message_index=0,
        role="tool",
        kind=Kind.LOG,
        text=text,
        first_line=1,
        line_severities=tuple("INFO" for _ in lines),
        identifiers=identifiers,
        identifier_lines=identifier_lines,
    )
    compacted = collapse_repeats(unit)
    output = compacted.splitlines()
    assert len(compacted) <= len(text)
    kept = [line for line in output if "similar lines omitted" not in line]
    omitted = sum(
        int(line.split()[1]) for line in output if "similar lines omitted" in line
    )
    assert len(kept) + omitted == len(lines)
    assert kept[0] == lines[0]
    assert kept[-1] == lines[-1]
    original_ids = [line for line in lines if has_identifier(line)]
    assert [line for line in kept if has_identifier(line)] == original_ids


def has_identifier(line: str) -> bool:
    return bool(find_identifiers(line, DEFAULT_IDENTIFIER_PATTERNS)[0])


LOOKAHEAD_HEX_ID = re.compile(r"\b(?=[0-9a-fA-F-]*\d)[0-9a-fA-F][0-9a-fA-F-]{7,}\b")
"""The digit-lookahead definition of a hexadecimal ID. It is quadratic on long
runs, so it serves only as an oracle on short text."""


@given(st.text(alphabet="0123456789abcdefABCDEF-xz _.:/", max_size=80))
def test_hex_id_masking_matches_the_lookahead_definition(text):
    assert _HEX_RUN.sub(_mask_hex_id, text) == LOOKAHEAD_HEX_ID.sub("<id>", text)


def minified(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


@given(JSON_VALUES)
def test_json_compaction_policies(value):
    assert json.loads(compact_json(value, "maximum_preservation")) == value
    balanced = compact_json(value, "balanced")
    assert expand(json.loads(balanced)) == value
    assert len(balanced) <= len(minified(value))
    compressed = compact_json(value, "maximum_compression")
    json.loads(compressed)
    assert len(compressed) <= len(minified(value))


@settings(max_examples=30)
@given(st.lists(st.integers(min_value=0, max_value=3), min_size=0, max_size=40))
def test_maximum_compression_never_invents_values(items):
    compressed = json.loads(compact_json(items, "maximum_compression"))
    values: set[object] = set()
    sampled = False
    for entry in compressed:
        if isinstance(entry, dict) and "__omitted__" in entry:
            sampled = True
        elif isinstance(entry, dict):
            values.add(entry["value"])
        else:
            values.add(entry)
    assert values <= set(items)
    if not sampled:
        assert values == set(items)
