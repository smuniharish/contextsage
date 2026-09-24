"""JSON structural detection.

Uses only the standard library ``json`` module — a dedicated JSON parsing
dependency is unnecessary for the confidence-scoring "does this look like
JSON" question ContextIQ needs to answer here, and keeps the dependency
footprint minimal.

``start_characters`` is overridable at construction time (no subclassing
required), the same way sibling parsers expose their own default patterns.
"""

from __future__ import annotations

import json

from contextiq.core.models import ContentSignals, RegionKind
from contextiq.parsers.base import ContentParser

_JSON_CONFIDENCE = 0.95

#: The built-in default: a JSON value must start with an object or array
#: opener. Exposed so callers can override it (e.g. to also accept a bare
#: leading quote for top-level JSON strings) without subclassing, and so
#: :class:`~contextiq.context.decomposition.ContextDecomposer` can derive
#: its own segmentation-time "where might JSON start" scan from the same
#: single source of truth.
DEFAULT_JSON_START_CHARACTERS = "{["


class JSONParser(ContentParser):
    """Detects a chunk of text that parses cleanly as a JSON object or array."""

    kind = RegionKind.JSON

    def __init__(self, *, start_characters: str = DEFAULT_JSON_START_CHARACTERS) -> None:
        self._start_characters = start_characters

    @property
    def start_characters(self) -> str:
        """The configured set of characters a JSON value may start with.

        Exposed so :class:`~contextiq.context.decomposition.ContextDecomposer`
        can derive its own segmentation-time JSON-start scan from whatever
        ``JSONParser`` is actually configured (default or overridden),
        rather than maintaining a second, independent copy.
        """
        return self._start_characters

    def detect(self, text: str) -> ContentSignals | None:
        if text[0] not in self._start_characters:
            return None
        try:
            json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return None
        return ContentSignals(kind=RegionKind.JSON, confidence=_JSON_CONFIDENCE)
