"""Deterministic log reduction.

Repeated low-value log lines may be safely collapsed; anything carrying
severity, an identifier, or being the first/last occurrence of a pattern is
always kept in full, uncollapsed.
"""

from __future__ import annotations

import re
from collections import defaultdict

from contextsage.classification.signals import normalize_for_repetition
from contextsage.exceptions import TransformationError

_SEVERITY_RE = re.compile(r"\b(ERROR|CRITICAL|FATAL|WARN(?:ING)?)\b")
_IDENTIFIER_HINT_RE = re.compile(
    r"\b(trace|request|correlation|txn|transaction)[_-]?id\b", re.IGNORECASE
)
_DEFAULT_COLLAPSE_THRESHOLD = 4


def reduce_log_block(text: str, collapse_threshold: int = _DEFAULT_COLLAPSE_THRESHOLD) -> str:
    """Collapse repetitive low-value log lines while always keeping signal lines.

    Raises:
        TransformationError: if the block cannot be safely processed (the
            caller must then leave the original content untouched).
    """
    try:
        lines = text.splitlines()
        if not lines:
            return text

        groups: dict[str, list[int]] = defaultdict(list)
        order: list[str] = []
        for idx, line in enumerate(lines):
            sig = normalize_for_repetition(line)
            if sig not in groups:
                order.append(sig)
            groups[sig].append(idx)

        keep = set()
        for sig in order:
            indices = groups[sig]
            representative = lines[indices[0]]
            always_keep = bool(_SEVERITY_RE.search(representative)) or bool(
                _IDENTIFIER_HINT_RE.search(representative)
            )
            if always_keep or len(indices) <= collapse_threshold:
                keep.update(indices)
            else:
                # Keep first and last occurrence; collapse the middle.
                keep.add(indices[0])
                keep.add(indices[-1])

        out_lines: list[str] = []
        omitted_run = 0
        for idx, line in enumerate(lines):
            if idx in keep:
                if omitted_run:
                    out_lines.append(f"... ({omitted_run} similar low-value lines omitted) ...")
                    omitted_run = 0
                out_lines.append(line)
            else:
                omitted_run += 1
        if omitted_run:
            out_lines.append(f"... ({omitted_run} similar low-value lines omitted) ...")
        return "\n".join(out_lines)
    except Exception as exc:  # pragma: no cover - defensive
        raise TransformationError(f"log reduction failed: {exc}") from exc
