"""Markdown/ASCII table structural detection.

No table-parsing dependency (e.g. ``pandas``) is justified for this
lightweight "does this look like a table" question — plain-text tool output
tables are almost always pipe-delimited Markdown-style tables, which a
couple of regexes detect reliably and conservatively.
"""

from __future__ import annotations

import re

from contextsage.core.models import ContentSignals, RegionKind
from contextsage.parsers.base import ContentParser

_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?[\s:|-]+\|[\s:|-]+\|?\s*$")

_MIN_LINES_FOR_STRUCTURE = 2
_MIN_TABLE_ROW_MATCHES = 2
_TABLE_CONFIDENCE = 0.9


class TableParser(ContentParser):
    """Detects pipe-delimited Markdown-style tables."""

    kind = RegionKind.TABLE

    def detect(self, text: str) -> ContentSignals | None:
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if len(lines) < _MIN_LINES_FOR_STRUCTURE:
            return None
        row_matches = sum(1 for ln in lines if _TABLE_ROW_RE.match(ln))
        has_separator = any(_TABLE_SEP_RE.match(ln) for ln in lines[:3])
        if row_matches >= _MIN_TABLE_ROW_MATCHES and has_separator:
            return ContentSignals(kind=RegionKind.TABLE, confidence=_TABLE_CONFIDENCE)
        return None
