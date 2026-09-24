"""Custom SQL content parser, built on a production-grade PyPI package.

ContextSage ships no built-in SQL parser (SQL is a domain-specific content
kind, not one of the general-purpose structural kinds every agent context
contains) -- exactly the extension point ``parsers`` exists for (see
``examples/all_parameters.py``'s ``EscalationTicketParser`` for the same
pattern with a fictitious ticket format). This example builds a *real* one.

Package choice: ``sqlglot`` (https://pypi.org/project/sqlglot/) over
``sqlparse``. ``sqlparse`` only tokenizes/formats -- it never validates
that text is *actually* well-formed SQL, so it would happily "tokenize"
arbitrary English too, reproducing exactly the false-confidence
misclassification risk a conservative classifier must avoid (the same
reason Pygments'
``guess_lexer`` was rejected for :class:`~contextsage.parsers.code_parser.CodeParser`).
``sqlglot`` is a real, dialect-aware parser/AST builder used in production
by data-lineage and SQL-transpilation tooling: it can actually raise a
``ParseError`` on malformed or non-SQL text, giving this parser the same
"cheap heuristic, then validate" shape as the built-in ``CodeParser``
(fence/heuristic first, tree-sitter validates second).

Uses a real chat model (see examples/_llm.py); requires EXPLABS_API_KEY.
"""

from __future__ import annotations

import re

import sqlglot
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from sqlglot import exp
from sqlglot.errors import SqlglotError

from _llm import build_demo_model
from contextsage import IntelligentSummarizationMiddleware
from contextsage.core.models import ContentSignals
from contextsage.parsers.base import ContentParser

#: Cheap, always-available first signal: does the text even *start* like a
#: SQL statement? Only when this matches does sqlglot's heavier, real
#: parse-and-validate step run -- sqlglot is never used to blind-guess
#: whether arbitrary untagged prose is SQL (a false positive is worse
#: than no classification). Overridable so an
#: application can recognize its own non-ANSI statement vocabulary (e.g.
#: ``UPSERT``) as SQL-like even when sqlglot itself cannot parse it in any
#: dialect.
DEFAULT_SQL_KEYWORD_PATTERN = re.compile(
    r"^\s*(WITH|SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|MERGE|EXEC(?:UTE)?)\b",
    re.IGNORECASE,
)

_KEYWORD_ONLY_CONFIDENCE = 0.5
_VALIDATED_CONFIDENCE = 0.93


class SQLContentParser(ContentParser):
    """Detects SQL statements via a keyword heuristic, validated by ``sqlglot``.

    Both the heuristic and the validation are overridable at construction
    time (no subclassing required), mirroring every built-in parser:

    * ``keyword_pattern`` -- which leading keywords count as "SQL-shaped".
    * ``dialect`` -- which ``sqlglot`` dialect (e.g. ``"tsql"``,
      ``"snowflake"``, ``"bigquery"``) validates the statement. Vendor SQL
      extensions (T-SQL's ``TOP n``, Snowflake's ``QUALIFY``, ...) are
      *invalid* in generic ANSI SQL, so the correct dialect must be
      supplied to recognize them with full confidence.
    """

    kind = "sql"

    def __init__(
        self,
        *,
        keyword_pattern: re.Pattern[str] = DEFAULT_SQL_KEYWORD_PATTERN,
        dialect: str | None = None,
    ) -> None:
        self._keyword_pattern = keyword_pattern
        self._dialect = dialect

    def detect(self, text: str) -> ContentSignals | None:
        stripped = text.strip()
        if not self._keyword_pattern.match(stripped):
            return None

        try:
            statements = sqlglot.parse(
                stripped, read=self._dialect, error_level=sqlglot.ErrorLevel.RAISE
            )
        except SqlglotError:
            # Keyword-shaped but not valid SQL in the configured dialect:
            # still worth flagging as SQL-like (better preserved than
            # silently compressed as plain text) but at lower confidence,
            # since it was never actually validated.
            return ContentSignals(kind=self.kind, confidence=_KEYWORD_ONLY_CONFIDENCE)

        tables = sorted(
            {t.name for stmt in statements if stmt is not None for t in stmt.find_all(exp.Table)}
        )
        return ContentSignals(
            kind=self.kind,
            confidence=_VALIDATED_CONFIDENCE,
            extra={"tables": tuple(tables), "dialect": self._dialect},
        )


def build_diagnostic_conversation() -> list:
    """Two ToolMessages: a raw (unfenced) SQL query, and a prose+log diagnosis.

    The SQL query is its own message (a realistic "query tool" result,
    distinct from a "log tool" result -- mirrors ``all_parameters.py``'s
    ``get_escalations``/``get_worker_logs`` split) so it reaches
    :class:`~contextsage.classification.signals.StructuralSignalDetector` as
    its own region, entirely as "everything else" text -- not fenced, not
    JSON -- where only a registered SQL parser can tell it apart from
    ``TEXT``.
    """
    sql_query = (
        "SELECT order_id, status, total FROM orders WHERE customer_id = 512 AND status = 'failed'"
    )
    diagnostic_output = (
        "Diagnostic query above returned 3 failed rows for customer 512.\n\n"
        "2024-07-01T00:00:00 ERROR nightly ETL job aborted after those failed rows"
    )
    return [
        HumanMessage(content="Why did last night's ETL job fail for customer 512?"),
        AIMessage(
            content="",
            tool_calls=[
                {"id": "call-1", "name": "run_diagnostic_query", "args": {}},
                {"id": "call-2", "name": "get_job_diagnosis", "args": {}},
            ],
        ),
        ToolMessage(content=sql_query, tool_call_id="call-1"),
        ToolMessage(content=diagnostic_output, tool_call_id="call-2"),
    ]


def demonstrate_classification() -> None:
    """Compare classification with and without the custom SQL parser registered."""
    conversation = build_diagnostic_conversation()

    baseline = IntelligentSummarizationMiddleware(model=build_demo_model(), trigger=("tokens", 5))
    baseline_units = baseline._decomposer.decompose(conversation)
    baseline_kinds = {str(u.signals.kind) for u in baseline_units}

    with_sql_parser = IntelligentSummarizationMiddleware(
        model=build_demo_model(), trigger=("tokens", 5), parsers=[SQLContentParser()]
    )
    sql_units = with_sql_parser._decomposer.decompose(conversation)
    sql_kinds = {str(u.signals.kind) for u in sql_units}
    sql_unit = next(u for u in sql_units if u.signals.kind == "sql")

    print("=== classification ===")
    print("default registry does NOT recognize 'sql' as a kind:", "sql" not in baseline_kinds)
    print("custom SQLContentParser recognizes it:", "sql" in sql_kinds)
    print("query correctly isolated into its own unit (not merged with prose/log):")
    print("   ", "SELECT order_id" in sql_unit.content and "ERROR" not in sql_unit.content)
    print("tables extracted from the validated parse:", sql_unit.signals.extra.get("tables"))


def demonstrate_dialect_override() -> None:
    """T-SQL's ``TOP`` clause: rejected by generic SQL, accepted with ``dialect="tsql"``."""
    tsql_query = "SELECT TOP 10 customer_id, total FROM orders WHERE customer_id = 512"

    generic_parser = SQLContentParser()
    tsql_parser = SQLContentParser(dialect="tsql")

    generic_signals = generic_parser.detect(tsql_query)
    tsql_signals = tsql_parser.detect(tsql_query)
    assert generic_signals is not None, "keyword pattern should still match TOP-clause SQL"
    assert tsql_signals is not None, "keyword pattern should still match TOP-clause SQL"

    print("=== dialect override (custom parser rules) ===")
    print(
        "generic dialect: keyword-shaped but fails real validation "
        f"(confidence={generic_signals.confidence}):",
        generic_signals.confidence == _KEYWORD_ONLY_CONFIDENCE,
    )
    print(
        f"dialect='tsql': validates cleanly (confidence={tsql_signals.confidence}) "
        "and extracts the table:",
        tsql_signals.confidence == _VALIDATED_CONFIDENCE
        and tsql_signals.extra.get("tables") == ("orders",),
    )


def demonstrate_keyword_pattern_override() -> None:
    """A non-ANSI ``UPSERT`` statement: invisible by default, SQL-shaped once overridden."""
    upsert_statement = "UPSERT INTO customers (id, name) VALUES (512, 'Acme Corp')"

    default_parser = SQLContentParser()
    custom_keyword_pattern = re.compile(
        rf"{DEFAULT_SQL_KEYWORD_PATTERN.pattern}|^\s*UPSERT\b", re.IGNORECASE
    )
    overridden_parser = SQLContentParser(keyword_pattern=custom_keyword_pattern)

    print("=== keyword_pattern override (custom regex) ===")
    print(
        "default keyword_pattern does not recognize UPSERT as SQL-shaped at all:",
        default_parser.detect(upsert_statement) is None,
    )
    overridden_signals = overridden_parser.detect(upsert_statement)
    print(
        "overridden keyword_pattern flags it as SQL-like "
        f"(confidence={overridden_signals.confidence if overridden_signals else None}), "
        "even though no dialect parses UPSERT:",
        overridden_signals is not None
        and overridden_signals.confidence == _KEYWORD_ONLY_CONFIDENCE,
    )


def demonstrate_end_to_end_summarization() -> None:
    """Full agent-facing run: the SQL region and its identifiers survive summarization."""
    conversation = build_diagnostic_conversation()
    noise = [
        HumanMessage(content=f"Also, unrelated question #{i}: what's the weather like?")
        for i in range(40)
    ]
    middleware = IntelligentSummarizationMiddleware(
        model=build_demo_model(),
        trigger=("tokens", 200),
        keep=("messages", 2),
        policy="maximum_preservation",
        parsers=[SQLContentParser()],
    )
    result = middleware.before_model({"messages": [*conversation, *noise]}, None)
    assert result is not None, "expected summarization to trigger"
    combined_text = "\n".join(str(getattr(m, "content", "")) for m in result["messages"])

    print("=== end-to-end: SQL survives real summarization ===")
    print("customer 512 identifier preserved:", "512" in combined_text)
    print("order_id column reference preserved:", "order_id" in combined_text)


def main() -> None:
    demonstrate_classification()
    demonstrate_dialect_override()
    demonstrate_keyword_pattern_override()
    demonstrate_end_to_end_summarization()


if __name__ == "__main__":
    main()
