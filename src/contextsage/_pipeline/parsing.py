"""The parsefabric configuration ContextSage uses to read agent context."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from parsefabric.builtins import JSONParser, MixedContentParser
from parsefabric.patterns import RegexPattern

from contextsage.errors import ConfigurationError

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from parsefabric import Parser
    from parsefabric.patterns import Pattern

_LEVEL = (
    r"(?P<level>TRACE|DEBUG|INFO|NOTICE|WARN(?:ING)?|ERROR|ERR|SEVERE|"
    r"CRIT(?:ICAL)?|FATAL|ALERT|EMERG(?:ENCY)?|PANIC)"
)
_ISO_TIMESTAMP = (
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:[.,]\d{1,9})?)?"
    r"(?:Z|[+-]\d{2}:?\d{2})?"
)
_MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
_SYSLOG_TIMESTAMP = rf"{_MONTH} {{1,2}}\d{{1,2}} \d{{2}}:\d{{2}}:\d{{2}}"
_CLOCK = r"\d{2}:\d{2}:\d{2}(?:[.,]\d{1,9})?"

TIMESTAMPED_LOG_LINE = (
    rf"^\s*[\[(]?(?:{_ISO_TIMESTAMP}|{_SYSLOG_TIMESTAMP}|{_CLOCK})[\])]?"
    rf"(?:[^\n]{{0,80}}?\b(?i:{_LEVEL})\b)?"
)
"""A line that starts with a timestamp, optionally followed by a level."""

LEVEL_LOG_LINE = rf"^\s*[\[(<]?{_LEVEL}[\])>]?(?::|\s|$)"
"""A line that starts with an upper-case level such as ``ERROR`` or ``[WARN]``."""

LOGFMT_LOG_LINE = (
    r"^(?=[^\n]*\blevel=\"?(?P<level>[A-Za-z]+))(?=[^\n]*\b(?:msg|message)=)"
)
"""A ``key=value`` line with ``level=`` and ``msg=`` fields."""

TRACEBACK_LINES = (
    r"^\s*Traceback \(most recent call last\):\s*$",
    r'^\s+File "[^"\n]+", line \d+(?:, in [^\n]+)?$',
    r"^\s+at \S[^\n]{0,500}(?:\)|:\d+:\d+)\s*$",
    r"^\s*(?:Caused by|Suppressed): [\w$.]+",
    r"^\s+\.\.\. \d+ (?:more|common frames omitted)\s*$",
    r"^(?:panic: |goroutine \d+ \[|fatal error: )",
    (
        r'^(?:Exception in thread "[^"\n]*" )?(?:[a-z_$][\w$]*\.)+[A-Z][\w$]*'
        r"(?:Exception|Error|Throwable)(?::[^\n]*)?$"
    ),
    r"^(?:[A-Za-z_]\w*\.)*[A-Z]\w*(?:Error|Exception|Exit|Interrupt)(?::[^\n]*)?$",
)
"""Lines of Python, JVM, Node.js and Go stack traces."""

TRACEBACK_LINE = (
    "^(?:"
    + "|".join(expression.removeprefix("^") for expression in TRACEBACK_LINES)
    + ")"
)
"""Any stack-trace line, as one expression so a line is tested once."""

TABLE_ROW = r"^\s*\|[^\n]*\|\s*$"
"""A Markdown or ASCII table row, including separator rows."""

JSON_START = (
    r'^\s*(?:\{\s*(?:"|\}|$)|\[\s*(?:[\[{"]|\]|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\s*[,\]]'
    r"|true\b|false\b|null\b|$))"
)
"""A line that opens a JSON object or array, but not ``[2024-01-01 ...]``."""

JSON_ROUTE = "contextsage-json"

_GRAMMAR_HELP = (
    "could not load the tree-sitter grammars used to detect code ({languages}): "
    "{error}. On an offline host, download them once while online with "
    '`python -c "import tree_sitter_language_pack as t; t.download({names})"` '
    "(they are cached per user), or pass code_languages=() to disable code detection."
)


def default_patterns() -> tuple[Pattern, ...]:
    """Return fresh line patterns for stack traces, logs and tables."""
    return (
        RegexPattern(
            "contextsage-traceback",
            TRACEBACK_LINE,
            priority=30,
            event_type="traceback",
            severity="ERROR",
        ),
        RegexPattern(
            "contextsage-log-timestamp",
            TIMESTAMPED_LOG_LINE,
            priority=20,
            event_type="log",
        ),
        RegexPattern(
            "contextsage-log-level", LEVEL_LOG_LINE, priority=20, event_type="log"
        ),
        RegexPattern(
            "contextsage-log-logfmt", LOGFMT_LOG_LINE, priority=20, event_type="log"
        ),
        RegexPattern("contextsage-table", TABLE_ROW, priority=10, event_type="table"),
    )


def build_parser(
    *,
    routes: Sequence[tuple[Pattern, Parser]],
    fence_routes: Mapping[str, Parser] | None,
    code_languages: Sequence[str],
) -> MixedContentParser:
    """Build the mixed-content parser for the given customizations.

    Caller routes are tried before ContextSage's JSON route, so a custom parser
    can claim lines that would otherwise be read as JSON.

    Args:
        routes: ``(selector, parser)`` pairs, tried first.
        fence_routes: Parsers for fenced code blocks, by language tag.
        code_languages: tree-sitter grammars used to detect unfenced code.

    Returns:
        The configured parser.

    Raises:
        ConfigurationError: If the configuration is invalid or the grammars
            cannot be loaded.
    """
    languages = (
        code_languages if isinstance(code_languages, str) else tuple(code_languages)
    )
    try:
        return MixedContentParser(
            default_patterns(),
            routes=(
                *routes,
                (RegexPattern(JSON_ROUTE, JSON_START), JSONParser()),
            ),
            fence_routes=fence_routes,
            code_languages=languages,
        )
    except (TypeError, ValueError, re.error) as error:
        raise ConfigurationError(
            f"invalid content parsing configuration: {error}"
        ) from error
    except Exception as error:
        raise ConfigurationError(
            _GRAMMAR_HELP.format(
                languages=", ".join(languages), error=error, names=list(languages)
            )
        ) from error
