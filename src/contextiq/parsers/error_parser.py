"""Error / stack-trace structural detection.

Runs last in the default registry: it deliberately overlaps with log
content (an ERROR-severity log line also matches error keywords), so a more
specific parser (JSON, table, code, log) should get first refusal.

Exception-class extraction uses the public grok ``JAVACLASS`` pattern
(:mod:`contextiq.parsers.grok_patterns`), which matches the shared
dotted-identifier-ending-in-Exception/Error shape used by Java, Python, and
most JVM/`.NET`-family stack traces.

All patterns are overridable at construction time (no subclassing
required): pass ``keyword_pattern``/``exception_class_pattern`` to
recognize an application's own error vocabulary or exception-naming
convention via the public API.
"""

from __future__ import annotations

import re

from contextiq.core.models import ContentSignals, RegionKind
from contextiq.parsers.base import ContentParser
from contextiq.parsers.grok_patterns import GROK_JAVACLASS

DEFAULT_ERROR_KEYWORD_PATTERN = re.compile(
    r"\b(traceback|exception|error|failed|failure|stack trace|panic)\b", re.IGNORECASE
)
DEFAULT_EXCEPTION_CLASS_PATTERN = GROK_JAVACLASS

_TRACEBACK_MARKER = "Traceback (most recent call last)"
_TRACEBACK_CONFIDENCE = 0.7
_KEYWORD_CONFIDENCE = 0.4


class ErrorParser(ContentParser):
    """Detects Python-style tracebacks and generic error/failure language."""

    kind = RegionKind.ERROR

    def __init__(
        self,
        *,
        keyword_pattern: re.Pattern[str] = DEFAULT_ERROR_KEYWORD_PATTERN,
        exception_class_pattern: re.Pattern[str] = DEFAULT_EXCEPTION_CLASS_PATTERN,
        traceback_marker: str = _TRACEBACK_MARKER,
    ) -> None:
        self._keyword_pattern = keyword_pattern
        self._exception_class_pattern = exception_class_pattern
        self._traceback_marker = traceback_marker

    def detect(self, text: str) -> ContentSignals | None:
        exception_class = self._first_exception_class(text)
        extra = {"exception_class": exception_class} if exception_class else {}

        if self._traceback_marker in text:
            return ContentSignals(
                kind=RegionKind.ERROR,
                confidence=_TRACEBACK_CONFIDENCE,
                has_error=True,
                extra=extra,
            )
        if self._keyword_pattern.search(text):
            return ContentSignals(
                kind=RegionKind.ERROR,
                confidence=_KEYWORD_CONFIDENCE,
                has_error=True,
                extra=extra,
            )
        return None

    def _first_exception_class(self, text: str) -> str | None:
        match = self._exception_class_pattern.search(text)
        return match.group(0) if match else None
