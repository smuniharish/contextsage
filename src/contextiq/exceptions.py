"""Exception hierarchy for ContextIQ.

All errors raised by ContextIQ inherit from :class:`ContextIQError` so callers can
catch a single base type, or a specific subtype when they need to react to a
particular failure category (budget analysis, planning, transformation, ...).

ContextIQ wraps errors at architectural boundaries (see ``docs/architecture.md``)
so provider-specific or LangGraph-specific exceptions do not leak into user code
unannounced. The original exception, when relevant, is always chained via
``raise ... from err`` so the underlying cause remains inspectable.
"""

from __future__ import annotations


class ContextIQError(Exception):
    """Base class for all ContextIQ errors."""


class BudgetError(ContextIQError):
    """Raised when the context budget cannot be computed or is misconfigured."""


class TokenCountingError(BudgetError):
    """Raised when token counting fails and no fallback estimate is available."""


class ClassificationError(ContextIQError):
    """Raised when structural signal detection fails unexpectedly.

    Detection failures are usually handled gracefully (content is left
    untouched); this exception is reserved for programming errors in a
    detector rather than "low confidence" outcomes.
    """


class PlanningError(ContextIQError):
    """Raised when the summarization planner cannot produce a valid plan."""


class TransformationError(ContextIQError):
    """Raised when a deterministic transformation fails.

    Transformation failures are optimizations; the transformation engine
    catches this internally per-unit and falls back to leaving the unit
    untouched. It is exposed publicly for observability and testing.
    """


class SummarizationError(ContextIQError):
    """Raised when the underlying LangGraph summarization step fails."""


class ValidationError(ContextIQError):
    """Raised when a produced summary fails post-summarization validation."""


class ReconstructionError(ContextIQError):
    """Raised when a valid LangGraph message history cannot be reconstructed."""


class ProvenanceError(ContextIQError):
    """Raised when langgraph-xai provenance/evidence recording or lookup fails."""


class RecoveryError(ContextIQError):
    """Raised when all recovery strategies are exhausted without a safe outcome."""
