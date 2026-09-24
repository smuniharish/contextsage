"""Deterministic structured-data (JSON) compaction.

No JSON framework is introduced; only the standard library ``json`` module
is used, to avoid an unnecessary dependency and keep the dependency
footprint minimal. Compaction is limited to:

* removing exact-duplicate list elements, and
* re-serializing with compact separators (no framework needed for this).

This module never guesses at which fields are semantically important —
that decision belongs to the preservation engine, upstream. It only removes
*exact* duplication and formatting overhead, which is always safe.
"""

from __future__ import annotations

import json

from contextsage.exceptions import TransformationError

_MAX_DEDUPED_EXAMPLES = 5


def compact_json(text: str) -> str:
    """Deduplicate exact-duplicate list entries and minify JSON formatting.

    Raises:
        TransformationError: if the text is not valid JSON, or compaction
            otherwise fails. Callers must fall back to the original text.
    """
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise TransformationError(f"not valid JSON: {exc}") from exc

    try:
        compacted = _compact_value(value)
        return json.dumps(compacted, separators=(",", ":"), default=str)
    except Exception as exc:  # pragma: no cover - defensive
        raise TransformationError(f"JSON compaction failed: {exc}") from exc


def _compact_value(value: object) -> object:
    if isinstance(value, list):
        return _compact_list(value)
    if isinstance(value, dict):
        return {k: _compact_value(v) for k, v in value.items()}
    return value


def _compact_list(items: list[object]) -> object:
    if len(items) <= _MAX_DEDUPED_EXAMPLES * 2:
        return [_compact_value(item) for item in items]

    seen: dict[str, object] = {}
    ordered_keys: list[str] = []
    for item in items:
        key = json.dumps(item, sort_keys=True, default=str)
        if key not in seen:
            seen[key] = item
            ordered_keys.append(key)

    unique_items = [_compact_value(seen[k]) for k in ordered_keys]
    if len(unique_items) == len(items):
        # No duplicates at all; still bound very large lists to a safe sample
        # plus an explicit summary of what was omitted.
        if len(unique_items) <= _MAX_DEDUPED_EXAMPLES * 2:
            return unique_items
        return {
            "_contextsage_truncated_list": True,
            "total_items": len(items),
            "sample_first": unique_items[:_MAX_DEDUPED_EXAMPLES],
            "sample_last": unique_items[-_MAX_DEDUPED_EXAMPLES:],
        }

    return {
        "_contextsage_deduplicated_list": True,
        "total_items": len(items),
        "unique_items": len(unique_items),
        "sample": unique_items[: _MAX_DEDUPED_EXAMPLES * 2],
    }
