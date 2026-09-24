"""Pluggable structural content parsers.

ContextSage ships a small set of conservative, dependency-light detectors —
one per file, one per structural kind — behind a common
:class:`~contextsage.parsers.base.ContentParser` abstract base class. This is
an *internal* extension point, not a public plugin
platform: ordinary users of :class:`contextsage.IntelligentSummarizationMiddleware`
never need to touch this package. It exists for advanced integrators who
want to add a domain-specific detector (e.g. a protobuf or SQL parser backed
by a specialized library) without forking or editing ContextSage's internals.

Adding a new parser is three steps:

1. Subclass :class:`~contextsage.parsers.base.ContentParser` in its own module.
2. Implement ``detect(text) -> ContentSignals | None``, returning ``None``
   when confidence is insufficient — false classification is
   worse than no classification.
3. Pass instances of it directly to
   ``IntelligentSummarizationMiddleware(parsers=[MyParser(), ...])`` — the
   middleware builds a :class:`~contextsage.parsers.base.ParserRegistry` from
   them (tried before the built-ins) and wires it into its internal
   ``StructuralSignalDetector``/``ContextDecomposer`` for you.

Built-in parsers are pure standard library plus ``tiktoken``/``tree-sitter``
(both core dependencies, never optional); :class:`~contextsage.parsers.code_parser.CodeParser`
uses ``tree-sitter`` only to validate an explicit fenced-code-block language
hint, or to refine a classification already reached by its own line-shape
heuristic — it never blind-guesses whether ambiguous untagged text is code.
"""

from __future__ import annotations

from contextsage.parsers.base import ContentParser, ParserRegistry, default_registry
from contextsage.parsers.code_parser import CodeParser
from contextsage.parsers.error_parser import ErrorParser
from contextsage.parsers.json_parser import JSONParser
from contextsage.parsers.log_parser import LogParser
from contextsage.parsers.table_parser import TableParser

__all__ = [
    "CodeParser",
    "ContentParser",
    "ErrorParser",
    "JSONParser",
    "LogParser",
    "ParserRegistry",
    "TableParser",
    "default_registry",
]
