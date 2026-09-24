"""Log-line structural detection.

Detection is anchored to public, well-known "grok" pattern building blocks
(:mod:`contextsage.parsers.grok_patterns`) — the same vocabulary
(``TIMESTAMP_ISO8601``, ``LOGLEVEL``, ...) used across the ELK/Logstash
ecosystem — rather than ad hoc regexes invented from scratch. Repetition-aware
reduction of detected log regions happens later, in
:mod:`contextsage.transformation.logs`.

The default patterns are overridable at construction time (no subclassing
required): pass ``timestamp_pattern``/``loglevel_pattern`` to recognize a
custom log format (e.g. a proprietary timestamp shape or an application's
own severity vocabulary) via the public API.
"""

from __future__ import annotations

import re

from contextsage.core.models import ContentSignals, RegionKind
from contextsage.parsers.base import ContentParser
from contextsage.parsers.grok_patterns import GROK_LOG_LINE, GROK_LOGLEVEL

_MIN_LINES_FOR_STRUCTURE = 2
_LOG_LINE_RATIO_THRESHOLD = 0.4
_LOG_CONFIDENCE_CAP = 0.95
_LOG_CONFIDENCE_BASE = 0.5

#: The built-in defaults, exposed so callers can compose with them (e.g.
#: ``re.compile(f"{DEFAULT_TIMESTAMP_PATTERN.pattern}|{my_pattern}")``)
#: instead of having to reconstruct the grok expansion themselves.
DEFAULT_TIMESTAMP_PATTERN = GROK_LOG_LINE
DEFAULT_LOGLEVEL_PATTERN = GROK_LOGLEVEL


class LogParser(ContentParser):
    """Detects a run of timestamped, severity-tagged log lines via grok patterns."""

    kind = RegionKind.LOG

    def __init__(
        self,
        *,
        timestamp_pattern: re.Pattern[str] = DEFAULT_TIMESTAMP_PATTERN,
        loglevel_pattern: re.Pattern[str] = DEFAULT_LOGLEVEL_PATTERN,
        min_lines: int = _MIN_LINES_FOR_STRUCTURE,
        ratio_threshold: float = _LOG_LINE_RATIO_THRESHOLD,
    ) -> None:
        self._timestamp_pattern = timestamp_pattern
        self._loglevel_pattern = loglevel_pattern
        self._min_lines = min_lines
        self._ratio_threshold = ratio_threshold

    @property
    def loglevel_pattern(self) -> re.Pattern[str]:
        """The configured severity/log-level pattern.

        Exposed so :class:`~contextsage.context.decomposition.ContextDecomposer`
        can derive its own segmentation-time "is this a log-like line"
        check from whatever ``LogParser`` is actually configured (default
        or overridden), rather than maintaining a second, independent copy.
        """
        return self._loglevel_pattern

    def detect(self, text: str) -> ContentSignals | None:
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if len(lines) < self._min_lines:
            return None
        log_like = sum(
            1
            for ln in lines
            if self._timestamp_pattern.search(ln) and self._loglevel_pattern.search(ln)
        )
        ratio = log_like / len(lines)
        if ratio >= self._ratio_threshold:
            confidence = min(_LOG_CONFIDENCE_CAP, _LOG_CONFIDENCE_BASE + ratio)
            return ContentSignals(kind=RegionKind.LOG, confidence=confidence)
        return None
