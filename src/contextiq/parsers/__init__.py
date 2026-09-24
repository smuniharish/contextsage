"""Pluggable structural content parsers.

ContextIQ ships a small set of conservative, dependency-light detectors —
one per file, one per structural kind — behind a common
:class:`~contextiq.parsers.base.ContentParser` abstract base class. This is
an *internal* extension point, not a public plugin
platform: ordinary users of :class:`contextiq.IntelligentSummarizationMiddleware`
never need to touch this package. It exists for advanced integrators who
want to add a domain-specific detector (e.g. a protobuf or SQL parser backed
by a specialized library) without forking or editing ContextIQ's internals.

Adding a new parser is three steps:

1. Subclass :class:`~contextiq.parsers.base.ContentParser` in its own module.
2. Implement ``detect(text) -> ContentSignals | None``, returning ``None``
   when confidence is insufficient — false classification is
   worse than no classification.
3. Pass instances of it directly to
   ``IntelligentSummarizationMiddleware(parsers=[MyParser(), ...])`` — the
   middleware builds a :class:`~contextiq.parsers.base.ParserRegistry` from
   them (tried before the built-ins) and wires it into its internal
   ``StructuralSignalDetector``/``ContextDecomposer`` for you.

Built-in parsers are pure standard library plus ``tiktoken``/``tree-sitter``
(both core dependencies, never optional); :class:`~contextiq.parsers.code_parser.CodeParser`
uses ``tree-sitter`` only to validate an explicit fenced-code-block language
hint, or to refine a classification already reached by its own line-shape
heuristic — it never blind-guesses whether ambiguous untagged text is code.
"""

from __future__ import annotations

from contextiq.parsers.base import ContentParser, ParserRegistry, default_registry
from contextiq.parsers.code_parser import CodeParser
from contextiq.parsers.error_parser import ErrorParser
from contextiq.parsers.json_parser import JSONParser
from contextiq.parsers.log_parser import LogParser
from contextiq.parsers.table_parser import TableParser

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
