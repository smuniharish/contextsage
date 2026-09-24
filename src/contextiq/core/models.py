"""Core internal domain models shared across ContextIQ's engines.

These types are the vocabulary every other package (context, budget,
importance, relationships, preservation, planning, transformation,
validation, recovery, lineage) is built on. They are intentionally *not*
exported from :mod:`contextiq` — the public surface of the package is
:class:`contextiq.IntelligentSummarizationMiddleware` only (see
``docs/api-reference.md`` for the rationale).

Dataclasses (rather than Pydantic models) are used here because these
objects are created in large numbers during context decomposition of very
large tool outputs and are internal, trusted, in-process data — validation
overhead is not needed and would materially hurt performance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RegionKind(StrEnum):
    """The structural nature of a :class:`ContextUnit`'s content.

    ContextIQ never assumes a whole message is one type. A
    single message is decomposed into regions, each independently classified.
    """

    TEXT = "text"
    JSON = "json"
    LOG = "log"
    CODE = "code"
    TABLE = "table"
    ERROR = "error"
    METADATA = "metadata"
    UNKNOWN = "unknown"

    # ``RegionKind`` covers the built-in structural kinds ContextIQ ships
    # with detectors for. Because it is a ``StrEnum``, any plain string is
    # also a valid runtime value for ``ContentSignals.kind`` (see its
    # ``RegionKind | str`` annotation) — a custom :class:`~contextiq.parsers.base.ContentParser`
    # is free to report a domain-specific kind (e.g. ``"sql"`` or
    # ``"protobuf"``) without needing to extend this enum. Engines that
    # dispatch on ``kind`` (e.g. the transformation engine) treat unknown
    # kinds conservatively: no registered handler means "leave untouched".


class PreservationLevel(StrEnum):
    """How aggressively a unit's content may be altered during summarization."""

    MUST_PRESERVE = "must_preserve"
    SHOULD_PRESERVE = "should_preserve"
    COMPRESSIBLE = "compressible"
    REDUNDANT = "redundant"
    SAFE_TO_DROP = "safe_to_drop"


class RelationType(StrEnum):
    """Kinds of relationships tracked between context units."""

    DEPENDS_ON = "depends_on"
    DERIVED_FROM = "derived_from"
    CAUSED_BY = "caused_by"
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    CORRECTED_BY = "corrected_by"
    FOLLOWS = "follows"
    PRECEDES = "precedes"
    PRODUCED_BY = "produced_by"
    REFERENCES = "references"


@dataclass(slots=True)
class ContentSignals:
    """Lightweight, opportunistic structural signals detected for a region.

    Detection is deliberately cheap and conservative:
    ``confidence`` below the caller's threshold means "treat as plain text".
    """

    kind: RegionKind | str = RegionKind.UNKNOWN
    confidence: float = 0.0
    is_repetitive: bool = False
    repetition_group: str | None = None
    identifiers: tuple[str, ...] = field(default_factory=tuple)
    has_error: bool = False
    severity: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ImportanceScore:
    """Composite importance signal for a context unit.

    ``value`` is a normalized score in ``[0, 1]``; ``reasons`` records which
    signals contributed, which powers observability and debugging (why was
    this unit kept/dropped?).
    """

    value: float
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not 0.0 <= self.value <= 1.0:
            msg = f"ImportanceScore.value must be in [0, 1], got {self.value!r}"
            raise ValueError(msg)


@dataclass(slots=True)
class Relationship:
    """A directed relationship between two context units."""

    source_unit_id: str
    target_unit_id: str
    relation: RelationType
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ContextUnit:
    """An analyzable slice of heterogeneous agent context.

    A single message may decompose into many ``ContextUnit`` instances (for
    example: an explanatory-text region, a JSON region, and a log region
    inside one large ``ToolMessage``). This is the internal unit of analysis
    for importance, preservation, relationships, and transformation.
    """

    unit_id: str
    message_id: str | None
    message_index: int
    role: str
    content: str
    token_count: int
    position: int = 0
    signals: ContentSignals = field(default_factory=ContentSignals)
    importance: ImportanceScore | None = None
    preservation: PreservationLevel = PreservationLevel.COMPRESSIBLE
    provenance_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BudgetReport:
    """Explicit accounting of the context window budget."""

    maximum_context_tokens: int
    reserved_output_tokens: int
    system_tokens: int
    tool_schema_tokens: int
    current_input_tokens: int
    safety_margin_tokens: int
    summarization_overhead_tokens: int = 0

    @property
    def available_input_tokens(self) -> int:
        available = (
            self.maximum_context_tokens
            - self.reserved_output_tokens
            - self.system_tokens
            - self.tool_schema_tokens
            - self.safety_margin_tokens
            - self.summarization_overhead_tokens
        )
        return max(available, 0)

    @property
    def overflow_tokens(self) -> int:
        return max(self.current_input_tokens - self.available_input_tokens, 0)

    @property
    def is_over_budget(self) -> bool:
        return self.overflow_tokens > 0

    @property
    def utilization(self) -> float:
        if self.available_input_tokens <= 0:
            return float("inf") if self.current_input_tokens > 0 else 0.0
        return self.current_input_tokens / self.available_input_tokens


@dataclass(slots=True)
class PlanTarget:
    """A single planned action against one or more context units."""

    unit_ids: tuple[str, ...]
    action: str  # "transform_deterministic" | "semantic_summarize" | "preserve_untouched"
    reason: str
    estimated_token_savings: int = 0


@dataclass(slots=True)
class SummarizationPlan:
    """The output of the :class:`~contextiq.planning.planner.SummarizationPlanner`."""

    required: bool
    trigger_reason: str
    overflow_tokens: int
    targets: tuple[PlanTarget, ...] = field(default_factory=tuple)
    must_preserve_unit_ids: tuple[str, ...] = field(default_factory=tuple)
    must_preserve_facts: tuple[str, ...] = field(default_factory=tuple)
    protected_message_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class ValidationFinding:
    """A single validation concern raised by :class:`SummaryValidator`."""

    severity: str  # "critical" | "warning"
    description: str
    fact: str | None = None


@dataclass(slots=True)
class ValidationResult:
    """Outcome of validating a produced summary against preservation requirements."""

    passed: bool
    findings: tuple[ValidationFinding, ...] = field(default_factory=tuple)

    @property
    def critical_findings(self) -> tuple[ValidationFinding, ...]:
        return tuple(f for f in self.findings if f.severity == "critical")


@dataclass(slots=True)
class RecoveryOutcome:
    """Result of a :class:`~contextiq.recovery.manager.RecoveryManager` attempt."""

    recovered: bool
    strategy: str
    fallback_used: bool = False
    detail: str = ""


@dataclass(slots=True)
class SummaryLineage:
    """Traceable metadata for a single summarization operation."""

    summary_id: str
    generation: int
    source_message_ids: tuple[str, ...]
    source_summary_ids: tuple[str, ...]
    created_at: str
    input_tokens: int
    prepared_tokens: int
    summary_tokens: int
    compression_ratio: float
    selected_target_count: int
    preservation_unit_count: int
    validation_status: str
    recovery_status: str
    fallback_used: bool
