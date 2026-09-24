"""Exception hierarchy for ContextSage.

All errors raised by ContextSage inherit from :class:`ContextSageError` so callers can
catch a single base type, or a specific subtype when they need to react to a
particular failure category (budget analysis, planning, transformation, ...).

ContextSage wraps errors at architectural boundaries (see ``docs/architecture.md``)
so provider-specific or LangGraph-specific exceptions do not leak into user code
unannounced. The original exception, when relevant, is always chained via
``raise ... from err`` so the underlying cause remains inspectable.
"""

from __future__ import annotations


class ContextSageError(Exception):
    """Base class for all ContextSage errors."""


class BudgetError(ContextSageError):
    """Raised when the context budget cannot be computed or is misconfigured."""


class TokenCountingError(BudgetError):
    """Raised when token counting fails and no fallback estimate is available."""


class ClassificationError(ContextSageError):
    """Raised when structural signal detection fails unexpectedly.

    Detection failures are usually handled gracefully (content is left
    untouched); this exception is reserved for programming errors in a
    detector rather than "low confidence" outcomes.
    """


class PlanningError(ContextSageError):
    """Raised when the summarization planner cannot produce a valid plan."""


class TransformationError(ContextSageError):
    """Raised when a deterministic transformation fails.

    Transformation failures are optimizations; the transformation engine
    catches this internally per-unit and falls back to leaving the unit
    untouched. It is exposed publicly for observability and testing.
    """


class SummarizationError(ContextSageError):
    """Raised when the underlying LangGraph summarization step fails."""


class ValidationError(ContextSageError):
    """Raised when a produced summary fails post-summarization validation."""


class ReconstructionError(ContextSageError):
    """Raised when a valid LangGraph message history cannot be reconstructed."""


class ProvenanceError(ContextSageError):
    """Raised when langgraph-xai provenance/evidence recording or lookup fails."""


class RecoveryError(ContextSageError):
    """Raised when all recovery strategies are exhausted without a safe outcome."""
