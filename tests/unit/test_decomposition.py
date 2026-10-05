from __future__ import annotations

import asyncio
import json
import re

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from parsefabric import ParseContext, ParsedEvent, Parser, ParseResult
from parsefabric.capabilities import ParserCapabilities
from parsefabric.models import Evidence
from parsefabric.patterns import RegexPattern

from contextsage._pipeline.decomposition import Decomposer, _classify
from contextsage._pipeline.models import Kind
from contextsage._pipeline.parsing import build_parser
from contextsage._pipeline.signals import DEFAULT_IDENTIFIER_PATTERNS
from tests.support.builders import heartbeat_log, units


def tool(content: str, message_id: str = "t1") -> ToolMessage:
    return ToolMessage(content, tool_call_id="call", id=message_id)


def kinds(text: str) -> list[str]:
    return [unit.kind for unit in units([tool(text)])]


def test_units_tile_the_message_exactly():
    text = (
        "\nIntro line.\n"
        + json.dumps({"status": "failed", "transaction_id": "TX-991"})
        + '\n\n{\n  "pretty": true\n}\n'
        + heartbeat_log(3)
        + "2024-01-01 10:00:00,123 - app - ERROR - boom\n"
        + "Traceback (most recent call last):\n"
        + '  File "app.py", line 3, in main\n'
        + "    raise ValueError('bad')\n"
        + "ValueError: bad\n"
        + "| a | b |\n|---|---|\n"
        + "Closing prose for customer 456."
    )
    decomposed = units([tool(text)])
    assert "".join(unit.text for unit in decomposed) == text
    assert [unit.kind for unit in decomposed] == [
        Kind.TEXT,
        Kind.JSON,
        Kind.JSON,
        Kind.LOG,
        Kind.LOG,
        Kind.ERROR,
        Kind.TABLE,
        Kind.TEXT,
    ]


def test_json_units_carry_the_decoded_document():
    decomposed = units([tool('{"items": [1, 2], "ok": true}')])
    assert decomposed[0].kind == Kind.JSON
    assert decomposed[0].document is not None
    assert decomposed[0].document.value == {"items": [1, 2], "ok": True}


def test_json_log_records_take_their_level_as_severity():
    decomposed = units([tool('{"level": "error", "msg": "boom"}')])
    assert decomposed[0].severity == "ERROR"
    assert decomposed[0].has_error


def test_invalid_json_is_text():
    assert kinds('{"unterminated": [1, 2\nnot json at all') == [Kind.TEXT]


def test_log_runs_split_by_severity_class():
    text = heartbeat_log(5) + "2024-08-01T04:00:00 WARN slow\n" + heartbeat_log(2)
    decomposed = units([tool(text)])
    assert [unit.kind for unit in decomposed] == [Kind.LOG, Kind.LOG, Kind.LOG]
    assert [unit.severity for unit in decomposed] == ["INFO", "WARNING", "INFO"]
    assert decomposed[1].first_line == 6


def test_blank_lines_join_the_previous_unit():
    decomposed = units([tool("\n\nfirst\n\n\nINFO log line\n\n")])
    assert [unit.text for unit in decomposed] == [
        "\n\nfirst\n\n\n",
        "INFO log line\n\n",
    ]


def test_indented_source_lines_inside_a_traceback_stay_in_it():
    text = (
        "Traceback (most recent call last):\n"
        '  File "app.py", line 3, in main\n'
        "    total = compute(order)\n"
        "ValueError: bad value\n"
    )
    decomposed = units([tool(text)])
    assert [unit.kind for unit in decomposed] == [Kind.ERROR]
    assert decomposed[0].line_severities == ("ERROR",) * 4


def test_unindented_lines_break_a_stack_trace():
    text = "ValueError: first\nplain prose between\nKeyError: second\n"
    assert kinds(text) == [Kind.ERROR, Kind.TEXT, Kind.ERROR]


def test_fenced_blocks_are_one_code_unit():
    text = "Fix:\n```python\nx = 1\n\nprint(x)\n```\nDone."
    decomposed = units([AIMessage(text, id="a1")])
    assert [unit.kind for unit in decomposed] == [Kind.TEXT, Kind.CODE, Kind.TEXT]
    assert decomposed[1].text == "```python\nx = 1\n\nprint(x)\n```\n"


def test_an_unclosed_fence_runs_to_the_end():
    decomposed = units([AIMessage("Start\n```\ncode line\nmore", id="a1")])
    assert decomposed[-1].kind == Kind.CODE
    assert decomposed[-1].text == "```\ncode line\nmore"


def test_identifiers_are_extracted_in_order_without_repeats():
    text = "Order ORD-12345 for customer 456; retry ORD-12345 (request_id=abc-1)."
    (unit,) = units([HumanMessage(text, id="h1")])
    assert unit.identifiers == ("ORD-12345", "request_id=abc-1", "customer 456")


def test_blank_messages_have_no_units():
    (unit,) = units([HumanMessage("   \n  ", id="h1"), HumanMessage("hi", id="h2")])
    assert (unit.unit_id, unit.message_index) == ("h2:0", 1)


def test_unit_ids_fall_back_to_the_message_index():
    (unit,) = units([HumanMessage("hello")])
    assert unit.unit_id == "message-0:0"
    assert unit.message_index == 0


def test_structured_content_is_decomposed_from_its_text():
    message = HumanMessage([{"type": "text", "text": "INFO a\nINFO b"}], id="h1")
    (unit,) = units([message])
    assert unit.kind == Kind.LOG


class SQLParser(Parser):
    """Recognizes SELECT statements and records its name, like built-in parsers."""

    @property
    def name(self) -> str:
        return "sql"

    @property
    def version(self) -> str:
        return "1"

    @property
    def capabilities(self) -> ParserCapabilities:
        return ParserCapabilities(deterministic=True, aggregatable=True)

    async def parse(
        self, source: object, context: ParseContext | None = None
    ) -> ParseResult:
        text = str(source)
        offset = context.source_offset if context and context.source_offset else 0
        event = self._with_parser_evidence(
            ParsedEvent("statement", attributes={"sql": text}),
            context,
            start_offset=offset,
            end_offset=offset + len(text.encode()),
            line_number=1,
        )
        return ParseResult(events=(event,))


class TicketParser(SQLParser):
    """A routed parser that does not record its name in the evidence."""

    @property
    def name(self) -> str:
        return "ticket"

    async def parse(
        self, source: object, context: ParseContext | None = None
    ) -> ParseResult:
        text = str(source)
        offset = context.source_offset if context and context.source_offset else 0
        event = ParsedEvent(
            "ticket_reference",
            evidence=Evidence(
                start_offset=offset,
                end_offset=offset + len(text.encode()),
                line_number=1,
            ),
        )
        return ParseResult(events=(event,))


def test_routed_parsers_contribute_their_own_kind():
    sql = SQLParser()
    parser = build_parser(
        routes=(
            (RegexPattern("select", r"^SELECT\b"), sql),
            (RegexPattern("ticket", r"^TICKET-\d+"), TicketParser()),
        ),
        fence_routes={"sql": sql},
        code_languages=(),
    )
    decomposer = Decomposer(parser, DEFAULT_IDENTIFIER_PATTERNS)
    text = "Query:\nSELECT id FROM orders\nTICKET-1 opened\n```sql\nSELECT 1\n```\n"
    decomposed = asyncio.run(decomposer.decompose([tool(text)]))
    assert [unit.kind for unit in decomposed] == [
        Kind.TEXT,
        "sql",
        "ticket_reference",
        "sql",
    ]


class BrokenParser(SQLParser):
    async def parse(
        self, source: object, context: ParseContext | None = None
    ) -> ParseResult:
        raise RuntimeError("parser crashed")


def test_a_failing_parser_leaves_the_message_as_one_text_unit():
    decomposer = Decomposer(BrokenParser(), DEFAULT_IDENTIFIER_PATTERNS)
    decomposed = asyncio.run(decomposer.decompose([tool("INFO a\nINFO b\n")]))
    assert [(unit.kind, unit.text) for unit in decomposed] == [
        (Kind.TEXT, "INFO a\nINFO b\n")
    ]


def test_events_without_a_line_number_are_ignored():
    classified = _classify(["one\n", "two\n"], [ParsedEvent("note")])
    assert classified.kinds == [Kind.TEXT, Kind.TEXT]


@pytest.mark.code_detection
def test_unfenced_code_is_detected_with_tree_sitter():
    parser = build_parser(routes=(), fence_routes=None, code_languages=("python",))
    decomposer = Decomposer(parser, (re.compile(r"\bTX-\d+\b"),))
    text = "Here is the fix.\ndef total(order):\n    return order.amount * 2\n"
    decomposed = asyncio.run(decomposer.decompose([AIMessage(text, id="a1")]))
    assert [unit.kind for unit in decomposed] == [Kind.TEXT, Kind.CODE]
