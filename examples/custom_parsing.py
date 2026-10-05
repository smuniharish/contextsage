"""Teach ContextSage a domain format with a parsefabric parser.

Run: python examples/custom_parsing.py

Requires sqlglot (installed with the ``examples`` dependency group). Nothing
here connects to a database or executes SQL.

``routes`` sends matching lines to your own parsefabric parser, and
``fence_routes`` does the same for fenced code blocks. Lines a route claims
become content of that parser's kind: below, the query and the suggested
index stop being generic ``code`` and become ``sql`` content.
"""

import sqlglot
from langchain_core.messages import AnyMessage, HumanMessage, ToolMessage
from langgraph.runtime import Runtime
from parsefabric import ParseContext, ParsedEvent, ParseIssue, ParseResult
from parsefabric.capabilities import ParserCapabilities
from parsefabric.parser import Parser
from parsefabric.patterns import RegexPattern
from sqlglot import exp
from sqlglot.errors import SqlglotError

from _models import scripted_model
from contextsage import IntelligentSummarizationMiddleware, SummarizationEvent


class SQLParser(Parser):
    """Recognize SQL statements with sqlglot and record the tables they touch."""

    @property
    def name(self) -> str:
        return "sql"

    @property
    def version(self) -> str:
        return "1"

    @property
    def capabilities(self) -> ParserCapabilities:
        return ParserCapabilities(
            deterministic=True, parallel_safe=True, aggregatable=True
        )

    async def parse(
        self, source: object, context: ParseContext | None = None
    ) -> ParseResult:
        text = source.decode() if isinstance(source, bytes) else str(source)
        start = context.source_offset if context and context.source_offset else 0
        span = {
            "start_offset": start,
            "end_offset": start + len(text.encode()),
            "line_number": 1,
        }
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


sql = SQLParser()
tool_output = (
    "Slow query report for the orders service.\n"
    "2026-10-04T09:00:00Z INFO query planner refreshed statistics\n"
    "SELECT o.id, c.email FROM orders o JOIN customers c ON c.id = o.customer_id\n"
    "2026-10-04T09:00:02Z WARN sequential scan on orders took 4100 ms\n"
    "Suggested index:\n"
    "```sql\n"
    "CREATE INDEX orders_customer_id ON orders (customer_id);\n"
    "```\n"
)
history: list[AnyMessage] = [
    HumanMessage("Why is the orders query slow?"),
    ToolMessage(tool_output, tool_call_id="call-1"),
]
events: list[SummarizationEvent] = []
summary_model = scripted_model("The user asked why the orders query is slow.")

built_in = IntelligentSummarizationMiddleware(
    model=summary_model,
    trigger=("messages", 2),
    keep=("messages", 1),
    observability_hook=events.append,
)
with_sql = IntelligentSummarizationMiddleware(
    model=summary_model,
    trigger=("messages", 2),
    keep=("messages", 1),
    routes=[(RegexPattern("select", r"(?i)^\s*(SELECT|WITH)\b"), sql)],
    fence_routes={"sql": sql},
    observability_hook=events.append,
)
for label, middleware in (
    ("built-in parsing only", built_in),
    ("with the SQL parser", with_sql),
):
    middleware.before_model({"messages": history}, Runtime())
    print(f"{label}: {events[-1].content_kinds}")
