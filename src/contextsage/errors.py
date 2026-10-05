"""Errors raised by ContextSage.

Summarization never fails an agent run: model errors, unparseable content and
provenance-store failures are recovered from internally and reported through
`contextsage.SummarizationEvent`. The errors below are raised only for invalid
configuration, when the middleware is constructed.
"""

from __future__ import annotations

__all__ = ["ConfigurationError", "ContextSageError"]


class ContextSageError(Exception):
    """Base class for every error raised by ContextSage."""


class ConfigurationError(ContextSageError, ValueError):
    """The middleware configuration is invalid or its resources are unavailable.

    Raised by `contextsage.IntelligentSummarizationMiddleware` for invalid
    arguments, and when the tree-sitter grammars used for code detection cannot
    be loaded (for example on an offline host without a grammar cache).
    """
