"""Customizing how ContextSage reads agent context with parsefabric.

ContextSage parses every message with a parsefabric `MixedContentParser`
built from `ParsingOptions`. Each option is a parsefabric extension point, so
anything parsefabric lets an application customize, ContextSage passes
through: line patterns, routed parsers (by object or by registry name),
fenced-block parsers, the code detector, the JSON codec, the lifecycle sink
and the execution backend.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from parsefabric import JSONCodec, ParseEngine, Parser
from parsefabric.builtins import DEFAULT_CODE_DETECTOR, CodeDetector, JSONParser, MixedContentParser
from parsefabric.execution import ExecutionBackend
from parsefabric.observability import ObservabilitySink
from parsefabric.patterns import Pattern, RegexPattern
from parsefabric.registry import ParserRegistry

from contextsage.errors import ConfigurationError

if TYPE_CHECKING:
    from parsefabric import Aggregate

__all__ = ["ParsingOptions", "default_patterns"]

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

LOGFMT_LOG_LINE = r"^(?=[^\n]*\blevel=\"?(?P<level>[A-Za-z]+))(?=[^\n]*\b(?:msg|message)=)"
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
    "^(?:" + "|".join(expression.removeprefix("^") for expression in TRACEBACK_LINES) + ")"
)
"""Any stack-trace line, as one expression so a line is tested once."""

TABLE_ROW = r"^\s*\|[^\n]*\|\s*$"
"""A Markdown or ASCII table row, including separator rows."""

JSON_START = (
    r'^\s*(?:\{\s*(?:"|\}|$)|\[\s*(?:[\[{"]|\]|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\s*[,\]]'
    r"|true\b|false\b|null\b|$))"
)
"""A line that opens a JSON object or array, but not ``[2024-01-01 ...]``."""


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
        RegexPattern("contextsage-log-level", LEVEL_LOG_LINE, priority=20, event_type="log"),
        RegexPattern("contextsage-log-logfmt", LOGFMT_LOG_LINE, priority=20, event_type="log"),
        RegexPattern("contextsage-table", TABLE_ROW, priority=10, event_type="table"),
    )


JSON_ROUTE = "contextsage-json"

_GRAMMAR_HELP = (
    "could not load the tree-sitter grammars used to detect code: {error}. On an offline "
    "host, download them once while online with "
    '`python -c "import tree_sitter_language_pack as t; t.prefetch({names})"` '
    "(they are cached per user), or pass ParsingOptions(code_detector=None) to disable "
    "code detection."
)


def _parser_or_name(value: object) -> bool:
    return isinstance(value, Parser) or (isinstance(value, str) and bool(value))


@dataclass(frozen=True, slots=True, kw_only=True)
class ParsingOptions:
    """How ContextSage parses message text, built from parsefabric extension points.

    Attributes:
        patterns: Line patterns for logs, stack traces and tables. ``None``
            uses `default_patterns`; pass ``[*default_patterns(), mine]`` to
            extend them.
        routes: ``(selector, parser)`` pairs tried before ContextSage's JSON
            route, so a custom parser can claim lines that would otherwise be
            read as JSON. A parser may be given by name, resolved through
            ``registry``. A routed parser's name becomes the content kind of
            the lines it parses. Use parsefabric's ``CLIOutputParser`` here to
            read command output with your own ``CommandOutputBackend``.
        fence_routes: Parsers for fenced code blocks, by lowercase language
            tag; also by object or registry name.
        code_detector: Recognizes unfenced code. Defaults to parsefabric's
            shared tree-sitter detector; ``None`` disables code detection.
        json_codec: Decoder for JSON documents, such as a faster third-party
            JSON library. Defaults to parsefabric's strict codec.
        registry: Resolves parser names in ``routes`` and ``fence_routes``.
        sink: Receives parsefabric's parse and execution lifecycle events.
            ContextSage's own events go to `contextsage.EventSink`.
        backend: Where CPU-bound analysis runs. Defaults to a worker thread
            owned by the summarizer, so analysis never blocks the event loop.
            A backend you pass is yours to shut down.
        max_concurrency: Messages parsed concurrently. Raise it for parsers
            that wait on I/O, such as model-backed semantic parsers.

    Raises:
        ConfigurationError: If an option has the wrong type, or a parser is
            named without a ``registry``.
    """

    patterns: Sequence[Pattern] | None = None
    routes: Sequence[tuple[Pattern, Parser[Aggregate] | str]] = ()
    fence_routes: Mapping[str, Parser[Aggregate] | str] = field(default_factory=dict)
    code_detector: CodeDetector | None = DEFAULT_CODE_DETECTOR
    json_codec: JSONCodec | None = None
    registry: ParserRegistry | None = None
    sink: ObservabilitySink | None = None
    backend: ExecutionBackend | None = None
    max_concurrency: int = 8

    def __post_init__(self) -> None:
        if self.patterns is not None and (
            isinstance(self.patterns, str)
            or not isinstance(self.patterns, Sequence)
            or not all(isinstance(pattern, Pattern) for pattern in self.patterns)
        ):
            raise ConfigurationError("patterns must be a sequence of parsefabric Patterns")
        if isinstance(self.routes, str) or not all(
            isinstance(route, tuple)
            and len(route) == 2
            and isinstance(route[0], Pattern)
            and _parser_or_name(route[1])
            for route in self.routes
        ):
            raise ConfigurationError("routes must be (Pattern, Parser or parser name) pairs")
        if not isinstance(self.fence_routes, Mapping) or not all(
            _parser_or_name(parser) for parser in self.fence_routes.values()
        ):
            raise ConfigurationError("fence_routes must map language tags to parsers or names")
        named = any(isinstance(parser, str) for _, parser in self.routes) or any(
            isinstance(parser, str) for parser in self.fence_routes.values()
        )
        checks: tuple[tuple[str, object, type], ...] = (
            ("code_detector", self.code_detector, CodeDetector),
            ("json_codec", self.json_codec, JSONCodec),
            ("registry", self.registry, ParserRegistry),
            ("sink", self.sink, ObservabilitySink),
            ("backend", self.backend, ExecutionBackend),
        )
        for name, value, expected in checks:
            if value is not None and not isinstance(value, expected):
                raise ConfigurationError(f"{name} must be a parsefabric {expected.__name__}")
        if named and self.registry is None:
            raise ConfigurationError("a parser given by name needs a registry")
        if (
            isinstance(self.max_concurrency, bool)
            or not isinstance(self.max_concurrency, int)
            or self.max_concurrency <= 0
        ):
            raise ConfigurationError("max_concurrency must be a positive integer")

    async def prepare(self) -> None:
        """Load the code detector's resources, such as tree-sitter grammars.

        The summarizer calls this before its first parse. Call it at start-up
        to fail fast on a host that cannot load them.

        Raises:
            ConfigurationError: If the detector cannot load its resources.
        """
        if self.code_detector is None:
            return
        try:
            await self.code_detector.prepare()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            languages = list(getattr(self.code_detector, "languages", ()))
            raise ConfigurationError(_GRAMMAR_HELP.format(error=error, names=languages)) from error

    async def build_parser(self) -> MixedContentParser[Aggregate]:
        """Build the mixed-content parser, resolving named parsers.

        Returns:
            The configured parser.

        Raises:
            ConfigurationError: If a named parser is not registered or
                parsefabric rejects the configuration.
        """
        try:
            routes = [(selector, await self._resolve(parser)) for selector, parser in self.routes]
            fences = {tag: await self._resolve(parser) for tag, parser in self.fence_routes.items()}
            return MixedContentParser(
                tuple(self.patterns) if self.patterns is not None else default_patterns(),
                routes=(
                    *routes,
                    (RegexPattern(JSON_ROUTE, JSON_START), JSONParser(codec=self.json_codec)),
                ),
                fence_routes=fences,
                code_detector=self.code_detector,
            )
        except ConfigurationError:
            raise
        except (LookupError, TypeError, ValueError, re.error) as error:
            raise ConfigurationError(f"invalid content parsing configuration: {error}") from error

    def build_engine(self) -> ParseEngine:
        """Return the parsefabric engine that reports to `sink`."""
        return ParseEngine(self.sink)

    async def _resolve(self, parser: Parser[Aggregate] | str) -> Parser[Aggregate]:
        if isinstance(parser, Parser):
            return parser
        # __post_init__ rejects a named parser without a registry.
        registry = cast("ParserRegistry", self.registry)
        try:
            return await registry.get(parser)
        except Exception as error:
            raise ConfigurationError(f"parser {parser!r} is not registered: {error}") from error
