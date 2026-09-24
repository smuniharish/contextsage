"""Structural signal detection.

Detection here is intentionally lightweight and conservative: this module
answers "what does this chunk of text look like?" with a confidence score,
not "parse this into a full AST". Low-confidence detections are treated as
plain text by callers — false structural classification is worse than no
classification.

Kind detection itself is delegated to a pluggable
:class:`~contextiq.parsers.base.ParserRegistry` (see :mod:`contextiq.parsers`):
:class:`StructuralSignalDetector` owns the *always-on* enrichment (identifier
extraction, error-keyword/severity tagging) that applies regardless of which
kind was detected, and never needs a mature parsing library itself — only
the Python standard library is used here, to keep the dependency footprint
minimal.

Classification is logically distinct from parsing (a parser decides *what
kind* a region is; the detector's own enrichment applies uniformly no
matter which kind was decided) and is therefore overridable independently:
all three patterns below are overridable at construction time (no
subclassing required), the same way parsers expose their own default
patterns — pass ``severity_pattern``/``error_keywords_pattern``/
``identifier_patterns`` to recognize an application's own severity
vocabulary or identifier conventions via the public API.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import replace

from contextiq.core.models import ContentSignals, RegionKind
from contextiq.parsers.base import ParserRegistry, default_registry

#: The built-in defaults, exposed so callers can override just one of them
#: (or compose with them) without having to reconstruct the others.
DEFAULT_SEVERITY_PATTERN = re.compile(r"\b(DEBUG|INFO|WARN(?:ING)?|ERROR|CRITICAL|FATAL|TRACE)\b")
DEFAULT_ERROR_KEYWORDS_PATTERN = re.compile(
    r"\b(traceback|exception|error|failed|failure|stack trace|panic)\b", re.IGNORECASE
)
DEFAULT_IDENTIFIER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"),
    re.compile(r"\b[A-Z]{2,6}-\d{3,}\b"),
    re.compile(r"\b(?:req|request|trace|correlation|txn|transaction)[_-]?id\s*[:=]\s*[\w-]+", re.I),
    re.compile(r"\bcustomer\s+\d+\b", re.I),
)


class StructuralSignalDetector:
    """Detects the structural nature of a chunk of text.

    ``registry`` is an optional, advanced extension point: pass a custom
    :class:`~contextiq.parsers.base.ParserRegistry` (built from your own
    :class:`~contextiq.parsers.base.ContentParser` subclasses, alongside or
    instead of the built-in ones) to plug in domain-specific detection
    without forking ContextIQ. The default registry (built-in JSON/table/
    code/log/error parsers) is used when ``registry`` is omitted, so ordinary
    usage of :class:`contextiq.IntelligentSummarizationMiddleware` never
    needs to know this exists.

    ``severity_pattern``, ``error_keywords_pattern``, and
    ``identifier_patterns`` override the always-on enrichment applied on top
    of whatever the registry detected; they default to
    :data:`DEFAULT_SEVERITY_PATTERN`, :data:`DEFAULT_ERROR_KEYWORDS_PATTERN`,
    and :data:`DEFAULT_IDENTIFIER_PATTERNS` respectively.
    """

    def __init__(
        self,
        registry: ParserRegistry | None = None,
        *,
        severity_pattern: re.Pattern[str] = DEFAULT_SEVERITY_PATTERN,
        error_keywords_pattern: re.Pattern[str] = DEFAULT_ERROR_KEYWORDS_PATTERN,
        identifier_patterns: Sequence[re.Pattern[str]] = DEFAULT_IDENTIFIER_PATTERNS,
    ) -> None:
        self._registry = registry or default_registry()
        self._severity_pattern = severity_pattern
        self._error_keywords_pattern = error_keywords_pattern
        self._identifier_patterns = tuple(identifier_patterns)

    @property
    def registry(self) -> ParserRegistry:
        """The configured parser registry.

        Exposed so :class:`~contextiq.context.decomposition.ContextDecomposer`
        can derive its own segmentation-time patterns from whichever
        parsers are actually registered (default or overridden via
        ``IntelligentSummarizationMiddleware(parsers=[...])``), rather than
        maintaining independent, possibly-stale copies.
        """
        return self._registry

    def detect(self, text: str) -> ContentSignals:
        stripped = text.strip()
        if not stripped:
            return ContentSignals(kind=RegionKind.TEXT, confidence=1.0)

        signals = self._registry.detect(stripped) or ContentSignals(
            kind=RegionKind.TEXT, confidence=0.5
        )
        identifiers = self._extract_identifiers(text)
        has_error = bool(self._error_keywords_pattern.search(text))
        severity_match = self._severity_pattern.search(text)
        return replace(
            signals,
            identifiers=identifiers,
            has_error=signals.has_error or has_error,
            severity=signals.severity
            or (severity_match.group(0).upper() if severity_match else None),
        )

    def _extract_identifiers(self, text: str) -> tuple[str, ...]:
        found: list[str] = []
        for pattern in self._identifier_patterns:
            found.extend(m.group(0) for m in pattern.finditer(text))
        # De-duplicate while preserving order.
        seen: set[str] = set()
        unique = []
        for item in found:
            if item not in seen:
                seen.add(item)
                unique.append(item)
        return tuple(unique)


def normalize_for_repetition(line: str) -> str:
    """Collapse volatile substrings (numbers, hex ids, timestamps) for dedup grouping."""
    normalized = re.sub(r"\b[0-9a-fA-F]{8,}\b", "<ID>", line)
    normalized = re.sub(r"\d+", "<N>", normalized)
    return normalized.strip()
