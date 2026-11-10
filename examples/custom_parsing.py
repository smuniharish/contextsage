"""Teach ContextSage a domain format with a parsefabric parser.

Run: python examples/custom_parsing.py

Requires sqlglot (installed with the ``examples`` dependency group). Nothing
here connects to a database or executes SQL.

``ParsingOptions.routes`` sends matching lines to your own parsefabric parser,
and ``fence_routes`` does the same for fenced code blocks. Lines a route
claims become content of that parser's kind: below, the query and the
suggested index stop being generic ``code`` and become ``sql`` content.
"""

from __future__ import annotations

import asyncio
from typing import override

import sqlglot
from _shared import ScriptedModel
from parsefabric import ParseContext, ParsedEvent, ParseIssue, ParseResult
from parsefabric.capabilities import ParserCapabilities
from parsefabric.parser import Parser
from parsefabric.patterns import RegexPattern
from sqlglot import exp
from sqlglot.errors import SqlglotError

from contextsage import ContextSummarizer, Message, ParsingOptions


class SQLParser(Parser):
    """Recognize SQL statements with sqlglot and record the tables they touch."""

    @property
    @override
    def name(self) -> str:
        return "sql"

    @property
    @override
    def version(self) -> str:
        return "1"

    @property
    @override
    def capabilities(self) -> ParserCapabilities:
        return ParserCapabilities(deterministic=True, parallel_safe=True, aggregatable=True)

    @override
    async def parse(self, source: object, context: ParseContext | None = None) -> ParseResult:
        text = source.decode() if isinstance(source, bytes) else str(source)
        start = context.source_offset if context and context.source_offset else 0
        span = {"start_offset": start, "end_offset": start + len(text.encode()), "line_number": 1}
        try:
            tables = sorted(
                {
                    table.name
                    for statement in sqlglot.parse(text, read="postgres")
                    if statement is not None
                    for table in statement.find_all(exp.Table)
                }
            )
        except SqlglotError as error:
            unparsed = ParsedEvent("unparsed", attributes={"text": text})
            return ParseResult(
                events=(self._with_parser_evidence(unparsed, context, **span),),
                errors=(ParseIssue.from_exception(error),),
            )
        event = ParsedEvent("sql_statement", attributes={"tables": [*tables]})
        return ParseResult(events=(self._with_parser_evidence(event, context, **span),))


TOOL_OUTPUT = (
    "Slow query report for the orders service.\n"
    "2026-10-04T09:00:00Z INFO query planner refreshed statistics\n"
    "SELECT o.id, c.email FROM orders o JOIN customers c ON c.id = o.customer_id\n"
    "2026-10-04T09:00:02Z WARN sequential scan on orders took 4100 ms\n"
    "Suggested index:\n"
    "```sql\n"
    "CREATE INDEX orders_customer_id ON orders (customer_id);\n"
    "```\n"
)
HISTORY = [
    Message("user", "Why is the orders query slow?"),
    Message("tool", TOOL_OUTPUT, tool_call_id="call-1"),
]


async def main() -> None:
    sql = SQLParser()
    with_sql = ParsingOptions(
        routes=[(RegexPattern("select", r"(?i)^\s*(SELECT|WITH)\b"), sql)],
        fence_routes={"sql": sql},
    )
    for label, parsing in (("built-in parsing only", None), ("with the SQL parser", with_sql)):
        async with ContextSummarizer(
            ScriptedModel("The user asked why the orders query is slow."),
            trigger=("messages", 2),
            keep=("messages", 1),
            parsing=parsing,
        ) as summarizer:
            result = await summarizer.summarize(HISTORY)
        if result is None:
            raise SystemExit("The history did not trigger summarization.")
        print(f"{label}: {result.event.content_kinds}")


if __name__ == "__main__":
    asyncio.run(main())
