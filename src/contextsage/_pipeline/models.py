"""Data shared by the pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping

    from langchain_core.messages import BaseMessage


class Kind:
    """Names of the built-in content kinds.

    Kinds are plain strings, because a routed custom parser contributes its own.
    """

    TEXT: Final = "text"
    JSON: Final = "json"
    LOG: Final = "log"
    CODE: Final = "code"
    TABLE: Final = "table"
    ERROR: Final = "error"


SUMMARY_ROLE: Final = "summary"
"""Role of units from summary messages.

A summary is a human message, but its text was written by the summary model,
so user signals such as corrections and instructions must not be read from it.
"""


class Preservation(StrEnum):
    """How freely a unit's content may be compacted."""

    MUST = "must_preserve"
    SHOULD = "should_preserve"
    COMPRESSIBLE = "compressible"


_SEVERITY_RANK = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
_SEVERITY_ALIASES = {
    "TRACE": "DEBUG",
    "NOTICE": "INFO",
    "WARN": "WARNING",
    "ERR": "ERROR",
    "SEVERE": "ERROR",
    "CRIT": "CRITICAL",
    "FATAL": "CRITICAL",
    "ALERT": "CRITICAL",
    "EMERG": "CRITICAL",
    "EMERGENCY": "CRITICAL",
    "PANIC": "CRITICAL",
}
HIGH_SEVERITY_RANK = _SEVERITY_RANK["ERROR"]
WARNING_RANK = _SEVERITY_RANK["WARNING"]


def canonical_severity(value: object) -> str | None:
    """Map a log level such as ``warn`` or ``FATAL`` to a canonical severity.

    Returns:
        ``DEBUG``, ``INFO``, ``WARNING``, ``ERROR`` or ``CRITICAL``, or ``None``
        when ``value`` is not a recognized level.
    """
    if not isinstance(value, str):
        return None
    level = value.strip().upper()
    level = _SEVERITY_ALIASES.get(level, level)
    return level if level in _SEVERITY_RANK else None


def severity_rank(severity: str | None) -> int:
    """Return a comparable rank for a canonical severity; 0 for none."""
    return _SEVERITY_RANK.get(severity or "", 0)


@dataclass(frozen=True, slots=True)
class ParsedJSON:
    """A decoded JSON document attached to a JSON unit."""

    value: object


@dataclass(frozen=True, slots=True)
class Unit:
    """A contiguous region of one message's text with a single content kind.

    Units tile their message exactly: concatenating the ``text`` of a message's
    units in order reproduces the message text. ``identifier_lines`` holds the
    indexes, within the unit, of the lines an identifier appears on.
    """

    unit_id: str
    message_index: int
    role: str
    kind: str
    text: str
    first_line: int
    line_severities: tuple[str | None, ...]
    identifiers: tuple[str, ...]
    document: ParsedJSON | None = None
    identifier_lines: frozenset[int] = frozenset()

    @property
    def severity(self) -> str | None:
        """The highest severity on any line of the unit."""
        return max(self.line_severities, key=severity_rank, default=None)

    @property
    def has_error(self) -> bool:
        """Whether the unit is an error report or has an error-level line."""
        return (
            self.kind == Kind.ERROR
            or severity_rank(self.severity) >= HIGH_SEVERITY_RANK
        )


@dataclass(frozen=True, slots=True)
class Importance:
    """A unit's importance in ``[0, 1]`` and the signals that produced it."""

    value: float
    reasons: frozenset[str]


@dataclass(frozen=True, slots=True)
class Contradiction:
    """Two messages asserting different values for the same key."""

    key: str
    unit_a: str
    value_a: str
    unit_b: str
    value_b: str


@dataclass(frozen=True, slots=True)
class Fact:
    """Information the rewritten history must still contain.

    Attributes:
        statement: The text restated verbatim if the fact goes missing.
        required: Strings that must all appear in a single message, as whole
            words and ignoring case, whitespace and apostrophe style, for the
            fact to count as preserved.
    """

    statement: str
    required: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Analysis:
    """Everything the pipeline learned about the history before summarizing."""

    units: tuple[Unit, ...]
    importance: Mapping[str, Importance]
    preservation: Mapping[str, Preservation]
    contradictions: tuple[Contradiction, ...]
    facts: tuple[Fact, ...]

    @property
    def must_preserve_count(self) -> int:
        """Number of units classified as must-preserve."""
        return sum(
            1 for level in self.preservation.values() if level is Preservation.MUST
        )

    def kind_counts(self) -> dict[str, int]:
        """Number of units per content kind, sorted by kind."""
        counts: dict[str, int] = {}
        for unit in self.units:
            counts[unit.kind] = counts.get(unit.kind, 0) + 1
        return dict(sorted(counts.items()))


@dataclass(frozen=True, slots=True)
class Prepared:
    """The history after deterministic compaction, with its analysis."""

    messages: list[BaseMessage]
    analysis: Analysis
    compacted_units: int
