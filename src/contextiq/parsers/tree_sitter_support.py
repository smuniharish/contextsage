"""Curated tree-sitter grammar registry for code detection.

Each supported language is backed by an official, individually-published
``tree-sitter-<language>`` PyPI package (maintained under the ``tree-sitter``
GitHub organization). These ship a *precompiled* native extension per
platform — parsing works fully offline with no runtime grammar download,
unlike aggregator packages that fetch grammars on demand. All packages
listed here are direct ContextIQ dependencies (see ``pyproject.toml``); a
missing grammar is treated as "this language isn't supported for real
parsing", never as an error.
"""

from __future__ import annotations

from functools import cache
from importlib import import_module

from tree_sitter import Language, Parser

# Fence-tag alias -> (module name, attribute on that module returning the
# raw PyCapsule language pointer). Aliases cover the common spellings agents
# and tool output use in fenced code blocks (```py, ```ts, ```js, ...).
_LANGUAGE_MODULES: dict[str, tuple[str, str]] = {
    "python": ("tree_sitter_python", "language"),
    "py": ("tree_sitter_python", "language"),
    "javascript": ("tree_sitter_javascript", "language"),
    "js": ("tree_sitter_javascript", "language"),
    "typescript": ("tree_sitter_typescript", "language_typescript"),
    "ts": ("tree_sitter_typescript", "language_typescript"),
    "tsx": ("tree_sitter_typescript", "language_tsx"),
    "go": ("tree_sitter_go", "language"),
    "golang": ("tree_sitter_go", "language"),
    "java": ("tree_sitter_java", "language"),
    "rust": ("tree_sitter_rust", "language"),
    "rs": ("tree_sitter_rust", "language"),
    "c": ("tree_sitter_c", "language"),
    "cpp": ("tree_sitter_cpp", "language"),
    "c++": ("tree_sitter_cpp", "language"),
    "ruby": ("tree_sitter_ruby", "language"),
    "rb": ("tree_sitter_ruby", "language"),
    "bash": ("tree_sitter_bash", "language"),
    "sh": ("tree_sitter_bash", "language"),
    "shell": ("tree_sitter_bash", "language"),
}

#: Try these (in order) when no explicit language hint is available. Kept
#: short and deliberately biased towards the languages most likely to show
#: up in agent tool output / patches, to bound worst-case parsing cost.
CANDIDATE_LANGUAGES: tuple[str, ...] = (
    "python",
    "javascript",
    "typescript",
    "go",
    "java",
    "rust",
    "c",
    "cpp",
    "ruby",
    "bash",
)


def normalize_language_name(name: str) -> str | None:
    """Map a fence-tag alias to a canonical supported language name, if any."""
    key = name.strip().lower()
    if key not in _LANGUAGE_MODULES:
        return None
    module_name, _ = _LANGUAGE_MODULES[key]
    # Canonical name is whatever CANDIDATE_LANGUAGES / the module family uses.
    return {
        "tree_sitter_python": "python",
        "tree_sitter_javascript": "javascript",
        "tree_sitter_typescript": "tsx" if key == "tsx" else "typescript",
        "tree_sitter_go": "go",
        "tree_sitter_java": "java",
        "tree_sitter_rust": "rust",
        "tree_sitter_c": "c",
        "tree_sitter_cpp": "cpp",
        "tree_sitter_ruby": "ruby",
        "tree_sitter_bash": "bash",
    }[module_name]


@cache
def get_parser(language: str) -> Parser | None:
    """Return a cached :class:`tree_sitter.Parser` for ``language``, or ``None``.

    ``None`` is returned (never raised) for any language name outside the
    curated set, or if the grammar module fails to import for any reason —
    code detection always has a non-tree-sitter fallback (fail-safe
    behavior).
    """
    entry = _LANGUAGE_MODULES.get(language.strip().lower())
    if entry is None:
        return None
    module_name, attr = entry
    try:
        module = import_module(module_name)
        raw_language = getattr(module, attr)()
        return Parser(Language(raw_language))
    except Exception:  # pragma: no cover - defensive; missing/broken grammar
        return None


def error_ratio(text: str, language: str) -> float | None:
    """Parse ``text`` as ``language`` and return the fraction of ERROR/MISSING nodes.

    ``None`` means "could not attempt" (unsupported language or parser
    failure) — callers must treat that as "no signal", not as a low ratio.
    A ratio of ``0.0`` is a genuinely clean parse.
    """
    parser = get_parser(language)
    if parser is None:
        return None
    try:
        tree = parser.parse(text.encode("utf-8", errors="replace"))
    except Exception:  # pragma: no cover - defensive
        return None
    total = 0
    errors = 0
    cursor = tree.walk()
    reached_root = False
    while not reached_root:
        node = cursor.node
        total += 1
        if node is not None and (node.type == "ERROR" or node.is_missing):
            errors += 1
        if cursor.goto_first_child():
            continue
        while not cursor.goto_next_sibling():
            if not cursor.goto_parent():
                reached_root = True
                break
    return errors / total if total else 1.0
