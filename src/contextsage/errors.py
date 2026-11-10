"""Errors raised by ContextSage.

Model errors, unparseable content and provenance-store failures are handled
internally and reported through `contextsage.SummarizationEvent`.
`ConfigurationError` reports invalid configuration or unavailable resources;
`ContextSageError` reports engine lifecycle errors.
"""

from __future__ import annotations

__all__ = ["ConfigurationError", "ContextSageError"]


class ContextSageError(Exception):
    """Base class for every error raised by ContextSage."""


class ConfigurationError(ContextSageError, ValueError):
    """The middleware configuration is invalid or its resources are unavailable.

    Raised by `contextsage.ContextSummarizer` or an integration for invalid
    arguments, and when parsing resources cannot be loaded during preparation.
    """
