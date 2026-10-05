"""Text signals shared by the pipeline: identifiers, failure language, repetition."""

from __future__ import annotations

import re
from bisect import bisect_right
from itertools import accumulate
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

DEFAULT_IDENTIFIER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
    ),
    re.compile(r"\b[A-Z]{2,6}-\d{3,}\b"),
    re.compile(
        r"\b(?:req|request|trace|span|correlation|txn|transaction|order|session)"
        r"[_-]?id\s*[:=]\s*[\"']?[\w-]+",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:customer|order|account|invoice|ticket|incident)\s+#?\d+\b", re.IGNORECASE
    ),
)
"""Built-in identifier formats: UUIDs, ``ABC-123`` keys, ``request_id=...``
assignments and phrases such as ``customer 456``."""

_FAILURE = re.compile(
    r"\b(?<!\bno )(?<!\bzero )(?<!\bwithout )(?<!\bnot )"
    r"(?:fail(?:s|ed|ing|ure|ures)?|errors?|exceptions?|crash(?:es|ed)?|"
    r"timed out|timeouts?|outages?|incidents?|root cause|panic(?:ked)?|"
    r"denied|refused|unavailable|aborted)\b",
    re.IGNORECASE,
)

_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:[.,]\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?"
    r"|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) {1,2}\d{1,2}"
    r" \d{2}:\d{2}:\d{2}"
    r"|\b\d{2}:\d{2}:\d{2}(?:[.,]\d+)?\b"
)
_HEX_RUN = re.compile(r"\b[0-9a-fA-F][0-9a-fA-F-]{7,}\b")
"""A run of eight or more hexadecimal digits and hyphens.

A run counts as an ID only if it contains a digit, which `_mask_hex_id`
checks: a lookahead for the digit would rescan the rest of the run from every
word boundary inside it, which is quadratic on input such as ``a-a-a-...``.
"""
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def _mask_hex_id(match: re.Match[str]) -> str:
    run = match.group()
    return "<id>" if any(character.isdigit() for character in run) else run


def find_identifiers(
    text: str, patterns: Sequence[re.Pattern[str]]
) -> tuple[tuple[str, ...], frozenset[int]]:
    """Find the identifiers in ``text`` and the lines they appear on.

    Returns:
        The identifiers, pattern by pattern in order of appearance and without
        repeats, and the indexes of the lines (as `str.splitlines` counts them)
        that any match touches.
    """
    found: dict[str, None] = {}
    lines: set[int] = set()
    starts: list[int] = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            found.setdefault(match.group(0), None)
            if not starts:
                starts = list(
                    accumulate(map(len, text.splitlines(keepends=True)), initial=0)
                )
            first = bisect_right(starts, match.start()) - 1
            last = bisect_right(starts, max(match.end() - 1, match.start())) - 1
            lines.update(range(first, last + 1))
    return tuple(found), frozenset(lines)


def mentions_failure(text: str) -> bool:
    """Whether ``text`` reports a failure ("timed out", "root cause", ...).

    Negated mentions such as "no errors" or "without failures" do not count.
    """
    return _FAILURE.search(text) is not None


def mask_volatile(text: str) -> str:
    """Replace timestamps and hexadecimal IDs with placeholders.

    No replacement spans a line break, so the result has the lines of ``text``.
    """
    return _HEX_RUN.sub(_mask_hex_id, _TIMESTAMP.sub("<ts>", text))


def mask_numbers(text: str) -> str:
    """Replace plain numbers with a placeholder, keeping the lines of ``text``."""
    return _NUMBER.sub("<n>", text)


def normalize_volatile(text: str) -> str:
    """Mask timestamps, hexadecimal IDs and numbers, and collapse whitespace.

    Texts that differ only in these volatile parts normalize to the same text,
    which is how repeated messages are recognized.
    """
    return " ".join(mask_numbers(mask_volatile(text)).split())
