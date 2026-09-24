"""Abstract base class and registry for pluggable structural content parsers.

See :mod:`contextsage.parsers` for the design rationale.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

    from contextsage.core.models import ContentSignals


class ContentParser(ABC):
    """A single, conservative structural detector for one content kind.

    Each parser answers "does this text look like *my* kind, and with what
    confidence?" — never "parse this into a full AST". A
    parser that is unsure must return ``None`` rather than guess; a false
    positive is worse than no classification.
    """

    #: The :class:`~contextsage.core.models.RegionKind` (or custom string) this
    #: parser detects. Used only for documentation/introspection — the actual
    #: kind returned is whatever ``detect()`` puts on the ``ContentSignals``.
    kind: str

    @abstractmethod
    def detect(self, text: str) -> ContentSignals | None:
        """Return signals if ``text`` matches this parser's kind, else ``None``.

        ``text`` is always non-empty, already-stripped content — the caller
        (:class:`~contextsage.classification.signals.StructuralSignalDetector`)
        handles the empty-text case itself.
        """


class ParserRegistry:
    """An ordered collection of :class:`ContentParser` instances.

    Parsers are tried in registration order; the first non-``None`` result
    wins (the "leave untouched unless confident" rule). This is
    intentionally a plain list-backed registry, not a ``PluginManager`` —
    this is an internal extension point by design, not a stable public API
    surface that requires registration ceremony for ordinary usage.
    """

    def __init__(self, parsers: tuple[ContentParser, ...] = ()) -> None:
        self._parsers = list(parsers)

    def register(self, parser: ContentParser) -> None:
        """Append a parser to the end of the try-order."""
        self._parsers.append(parser)

    def detect(self, text: str) -> ContentSignals | None:
        """Return the first non-``None`` detection across registered parsers."""
        for parser in self._parsers:
            signals = parser.detect(text)
            if signals is not None:
                return signals
        return None

    def __iter__(self) -> Iterator[ContentParser]:
        return iter(self._parsers)

    def __len__(self) -> int:
        return len(self._parsers)


def default_registry() -> ParserRegistry:
    """Build the registry ContextSage uses out of the box.

    Order matters: JSON and table detection are the most structurally
    unambiguous, so they run first; code and log detection are heuristic and
    run next; error detection (which can overlap with log content) runs
    last so it only fires when nothing more specific already matched.
    """
    # Imported lazily to avoid a module-level import cycle: each parser
    # module imports ``ContentParser`` from this module.
    from contextsage.parsers.code_parser import CodeParser  # noqa: PLC0415
    from contextsage.parsers.error_parser import ErrorParser  # noqa: PLC0415
    from contextsage.parsers.json_parser import JSONParser  # noqa: PLC0415
    from contextsage.parsers.log_parser import LogParser  # noqa: PLC0415
    from contextsage.parsers.table_parser import TableParser  # noqa: PLC0415

    return ParserRegistry(
        (
            JSONParser(),
            TableParser(),
            CodeParser(),
            LogParser(),
            ErrorParser(),
        )
    )
