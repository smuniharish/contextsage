"""Code structural detection.

Two independent signals are combined, and both are pluggable via
constructor overrides so advanced integrators can tune detection for their
own tool-output conventions without subclassing:

1. A cheap regex heuristic (default: fenced code blocks, or a line-shape
   heuristic matching common declaration/import keywords) — the sole basis
   for the CODE/not-CODE decision itself, always available, zero cost.
2. Real syntax-aware validation via ``tree-sitter`` (direct dependency; see
   :mod:`contextsage.parsers.tree_sitter_support`): once (1) already believes
   the text is code — via an explicit fence-tag hint, or via the line-shape
   heuristic — tree-sitter is used to *validate a stated language* or
   *refine which of the candidate languages best fits*, by actually parsing
   the text and measuring the fraction of ERROR/MISSING nodes.

Tree-sitter is deliberately **never** used to blind-guess whether ambiguous,
untagged text is code at all: several grammars (notably shells) are
permissive enough to "cleanly parse" arbitrary plain English with a 0%
error ratio (verified empirically), which would reproduce exactly the kind
of false-confidence misclassification that ruled out Pygments'
``guess_lexer`` for this same purpose: a false positive is
worse than no classification.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from contextsage.core.models import ContentSignals, RegionKind
from contextsage.parsers.base import ContentParser
from contextsage.parsers.tree_sitter_support import (
    CANDIDATE_LANGUAGES,
    error_ratio,
    normalize_language_name,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

DEFAULT_CODE_FENCE_PATTERN = re.compile(r"```")
DEFAULT_TAGGED_FENCE_PATTERN = re.compile(r"```([A-Za-z0-9_+-]+)\s*\n")
DEFAULT_CODE_HEURISTIC_PATTERN = re.compile(
    r"^\s*(def |class |import |from |function |const |let |var |public |private |#include)"
)

_CODE_LINE_RATIO_THRESHOLD = 0.2
_FENCE_CONFIDENCE = 0.85
_HEURISTIC_CONFIDENCE = 0.6
_TREE_SITTER_CONFIDENCE = 0.92
_TREE_SITTER_MIN_CHARS = 8
_CLEAN_PARSE_ERROR_RATIO = 0.05


class CodeParser(ContentParser):
    """Detects source code via fenced blocks, a line heuristic, or tree-sitter.

    All default patterns/config are overridable at construction time — no
    subclassing required:

    * ``fence_pattern`` / ``tagged_fence_pattern`` — how fenced code blocks
      (and their optional language tag) are recognized.
    * ``heuristic_pattern`` / ``heuristic_ratio_threshold`` — the
      always-available line-shape fallback.
    * ``candidate_languages`` — which tree-sitter grammars are tried, in
      order, when no language tag is present.
    * ``error_ratio_threshold`` — how clean a tree-sitter parse must be
      (fraction of ERROR/MISSING nodes) to count as a confident match.
    """

    kind = RegionKind.CODE

    def __init__(
        self,
        *,
        fence_pattern: re.Pattern[str] = DEFAULT_CODE_FENCE_PATTERN,
        tagged_fence_pattern: re.Pattern[str] = DEFAULT_TAGGED_FENCE_PATTERN,
        heuristic_pattern: re.Pattern[str] = DEFAULT_CODE_HEURISTIC_PATTERN,
        heuristic_ratio_threshold: float = _CODE_LINE_RATIO_THRESHOLD,
        candidate_languages: Sequence[str] = CANDIDATE_LANGUAGES,
        error_ratio_threshold: float = _CLEAN_PARSE_ERROR_RATIO,
    ) -> None:
        self._fence_pattern = fence_pattern
        self._tagged_fence_pattern = tagged_fence_pattern
        self._heuristic_pattern = heuristic_pattern
        self._heuristic_ratio_threshold = heuristic_ratio_threshold
        self._candidate_languages = tuple(candidate_languages)
        self._error_ratio_threshold = error_ratio_threshold

    @property
    def fence_pattern(self) -> re.Pattern[str]:
        """The configured fence-marker pattern (e.g. ``` ``` ```).

        Exposed so :class:`~contextsage.context.decomposition.ContextDecomposer`
        can derive its own segmentation-time fence-block-extraction regex
        from whatever ``CodeParser`` is actually configured (default or
        overridden), rather than maintaining a second, independent copy.
        """
        return self._fence_pattern

    def detect(self, text: str) -> ContentSignals | None:
        fenced = self._detect_fenced(text)
        if fenced is not None:
            return fenced

        return self._detect_heuristic(text)

    def _detect_fenced(self, text: str) -> ContentSignals | None:
        if not self._fence_pattern.search(text):
            return None
        tagged = self._tagged_fence_pattern.search(text)
        language_hint = tagged.group(1) if tagged else None
        canonical = normalize_language_name(language_hint) if language_hint else None
        extra: dict[str, object] = {"language": language_hint} if language_hint else {}
        if canonical is not None:
            # A stated, recognized language tag: validate it actually parses
            # cleanly rather than trusting the tag blindly.
            # Tree-sitter is used *only* to check an already-stated hint here
            # — never to blind-guess a language for untagged text, since
            # several grammars (notably shells) are permissive enough to
            # "cleanly parse" arbitrary plain English (verified empirically),
            # which is exactly the kind of false-confidence classification
            # ContextSage must avoid.
            ratio = error_ratio(text, canonical)
            if ratio is not None and ratio <= self._error_ratio_threshold:
                extra["tree_sitter_language"] = canonical
                return ContentSignals(
                    kind=RegionKind.CODE, confidence=_TREE_SITTER_CONFIDENCE, extra=extra
                )
        return ContentSignals(kind=RegionKind.CODE, confidence=_FENCE_CONFIDENCE, extra=extra)

    def _detect_heuristic(self, text: str) -> ContentSignals | None:
        lines = text.splitlines()
        code_like = sum(1 for ln in lines if self._heuristic_pattern.match(ln))
        if not lines or code_like / len(lines) <= self._heuristic_ratio_threshold:
            return None
        # The line-shape heuristic already gives an independent, non-tree-sitter
        # reason to believe this is code; tree-sitter is then used only to
        # *refine* which language it is (best-fit among the candidates),
        # never to establish the CODE classification itself.
        best_language = self._best_matching_language(text)
        extra = {"tree_sitter_language": best_language} if best_language else {}
        confidence = _TREE_SITTER_CONFIDENCE if best_language else _HEURISTIC_CONFIDENCE
        return ContentSignals(kind=RegionKind.CODE, confidence=confidence, extra=extra)

    def _best_matching_language(self, text: str) -> str | None:
        if len(text) < _TREE_SITTER_MIN_CHARS:
            return None
        best_language: str | None = None
        best_ratio = self._error_ratio_threshold
        for language in self._candidate_languages:
            ratio = error_ratio(text, language)
            if ratio is not None and ratio <= best_ratio:
                best_language = language
                best_ratio = ratio
        return best_language
