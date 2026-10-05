"""Preservation levels and the facts a rewritten history must keep."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from contextsage._pipeline.importance import (
    CONSTRAINT,
    CORRECTION,
    normalize_apostrophes,
)
from contextsage._pipeline.models import Fact, Preservation

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from contextsage._pipeline.models import Contradiction, Importance, Unit

type Policy = Literal["balanced", "maximum_preservation", "maximum_compression"]
POLICIES: tuple[Policy, ...] = (
    "balanced",
    "maximum_preservation",
    "maximum_compression",
)


@dataclass(frozen=True, slots=True)
class _Thresholds:
    must: float
    should: float
    error_must: float


_THRESHOLDS: Mapping[Policy, _Thresholds] = {
    "maximum_preservation": _Thresholds(must=0.60, should=0.30, error_must=0.45),
    "balanced": _Thresholds(must=0.75, should=0.45, error_must=0.60),
    "maximum_compression": _Thresholds(must=0.90, should=0.65, error_must=0.80),
}
_STRUCTURAL_REASONS = frozenset(
    {"user_correction", "user_identifier", "identifier_in_failure_context"}
)
_CORRECTED_VALUE = re.compile(
    r"(?<!n't\s)(?<!not\s)\b(?:use|switch\s+to|change\s+(?:it|that|this)\s+to|"
    r"i\s+meant|actually,?\s+(?:use|it'?s|make\s+it))\s++"
    r"(?P<value>[^.,;!?\n]{1,60}?)(?=\s++instead\b|\s*+[.,;!?\n]|\s*+$)",
    re.IGNORECASE,
)
_REPLACED_VALUE = re.compile(
    r"\binstead\s+of\s++(?P<value>[^.,;!?\n]{1,60}?)(?=\s*+[.,;!?\n]|\s*+$)",
    re.IGNORECASE,
)
"""Possessive whitespace quantifiers keep both patterns linear on long runs of
spaces, which the value's character class also matches."""
_SENTENCE_LIMIT = 200
_WORD = re.compile(r"\S+")


def classify(
    units: Sequence[Unit],
    importance: Mapping[str, Importance],
    contradictions: Sequence[Contradiction],
    policy: Policy,
) -> dict[str, Preservation]:
    """Assign a preservation level to every unit.

    A unit is must-preserve for a structural reason (a user correction, an
    identifier the user stated or one in a failure context, or a side of a
    contradiction) regardless of policy. Otherwise its importance is compared
    with the policy's thresholds; repetitive units are always compressible.

    Args:
        units: Units in history order.
        importance: Importance by unit ID.
        contradictions: Detected contradictions.
        policy: The preservation policy.

    Returns:
        The preservation level of each unit, by unit ID.
    """
    thresholds = _THRESHOLDS[policy]
    contradicting = {c.unit_a for c in contradictions} | {
        c.unit_b for c in contradictions
    }
    levels: dict[str, Preservation] = {}
    for unit in units:
        score = importance[unit.unit_id]
        if unit.unit_id in contradicting or score.reasons & _STRUCTURAL_REASONS:
            level = Preservation.MUST
        elif "repetitive_low_value" in score.reasons:
            level = Preservation.COMPRESSIBLE
        elif score.value >= thresholds.must or (
            "error_severity" in score.reasons and score.value >= thresholds.error_must
        ):
            level = Preservation.MUST
        elif score.value >= thresholds.should:
            level = Preservation.SHOULD
        else:
            level = Preservation.COMPRESSIBLE
        levels[unit.unit_id] = level
    return levels


def _sentence(text: str, match: re.Match[str]) -> str | None:
    """Return the sentence or line containing ``match``, as whole words.

    A sentence longer than the limit is narrowed to the words around the
    match, so it stays short and still matches its source as whole words.

    Returns:
        The sentence with whitespace collapsed, or ``None`` when the matched
        word alone exceeds the limit.
    """
    start = max(
        text.rfind("\n", 0, match.start()),
        *(text.rfind(mark, 0, match.start()) for mark in (". ", "! ", "? ")),
    )
    start = 0 if start < 0 else start + 1
    ends = [
        position
        for position in (
            text.find(mark, match.end()) for mark in ("\n", ". ", "! ", "? ")
        )
        if position >= 0
    ]
    end = min(ends) + 1 if ends else len(text)
    words = [(word.end(), word.group()) for word in _WORD.finditer(text, start, end)]
    first = next(index for index, (stop, _) in enumerate(words) if stop > match.start())
    last, length = first + 1, len(words[first][1])
    if length > _SENTENCE_LIMIT:
        return None
    while True:
        before = length
        if last < len(words) and length + 1 + len(words[last][1]) <= _SENTENCE_LIMIT:
            length += 1 + len(words[last][1])
            last += 1
        if first > 0 and length + 1 + len(words[first - 1][1]) <= _SENTENCE_LIMIT:
            first -= 1
            length += 1 + len(words[first][1])
        if length == before:
            return " ".join(word for _, word in words[first:last])


def extract_facts(
    units: Sequence[Unit],
    importance: Mapping[str, Importance],
    preservation: Mapping[str, Preservation],
    contradictions: Sequence[Contradiction],
    *,
    carried: Sequence[Fact],
) -> tuple[Fact, ...]:
    """Collect the facts validation will require, in history order.

    Facts come from must-preserve units: every identifier, each user correction
    (required: the corrected value) and each standing instruction (required:
    the instruction itself), plus both values of every contradiction. Facts
    that earlier summaries recorded are carried forward unchanged. An
    identifier that a user correction replaced is not restated on its own,
    since the correction already records it.

    Args:
        units: Units in history order.
        importance: Importance by unit ID.
        preservation: Preservation level by unit ID.
        contradictions: Detected contradictions.
        carried: Facts recorded by the summaries in the history.

    Returns:
        Unique facts in history order.
    """
    facts: dict[str, Fact] = {}
    replaced = {
        match.group("value").strip().casefold()
        for unit in units
        if "user_correction" in importance[unit.unit_id].reasons
        for match in _REPLACED_VALUE.finditer(normalize_apostrophes(unit.text))
    }

    def add(fact: Fact) -> None:
        if fact.statement.casefold() not in replaced:
            facts.setdefault(fact.statement, fact)

    for fact in carried:
        add(fact)
    for unit in units:
        if preservation[unit.unit_id] is not Preservation.MUST:
            continue
        for identifier in unit.identifiers:
            add(Fact(identifier, (identifier,)))
        reasons = importance[unit.unit_id].reasons
        text = normalize_apostrophes(unit.text)
        if (
            "user_correction" in reasons
            and (match := CORRECTION.search(text))
            and (sentence := _sentence(text, match))
        ):
            value = _CORRECTED_VALUE.search(sentence)
            required = (value.group("value").strip() if value else "") or sentence
            add(Fact(f'User correction: "{sentence}"', (required,)))
        if (
            "active_constraint" in reasons
            and (match := CONSTRAINT.search(text))
            and (sentence := _sentence(text, match))
        ):
            add(Fact(f'User instruction: "{sentence}"', (sentence,)))
    for contradiction in contradictions:
        add(
            Fact(
                f"Conflicting values reported for {contradiction.key}: "
                f"{contradiction.value_a} (earlier) vs {contradiction.value_b} (later)",
                (contradiction.value_a, contradiction.value_b),
            )
        )
    return tuple(facts.values())
