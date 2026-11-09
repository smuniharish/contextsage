"""ContextSage: information-aware context summarization for AI agents.

ContextSage parses heterogeneous agent context with parsefabric, keeps what
matters, compacts what is repetitive, has a language model write the summary,
verifies that nothing important was lost, and records provenance with agxai.
It is framework-agnostic: use `ContextSummarizer` directly, adapt any
framework with a `FrameworkAdapter`, or use an integration such as
``contextsage.integrations.langchain``.

    from contextsage import ContextSummarizer
"""

import logging
from importlib.metadata import PackageNotFoundError, version

from contextsage._pipeline.signals import DEFAULT_IDENTIFIER_PATTERNS
from contextsage._pipeline.summary import DEFAULT_SUMMARY_PROMPT
from contextsage.contracts import (
    EventSink,
    FrameworkAdapter,
    JSONCompaction,
    PreservationPolicy,
    PreservationThresholds,
    TokenCounter,
)
from contextsage.engine import ContextSummarizer, SummarizationResult
from contextsage.errors import ConfigurationError, ContextSageError
from contextsage.events import RecoveryStatus, SummarizationEvent, ValidationStatus
from contextsage.messages import Fact, Message, Role, SummaryLineage, ToolCall
from contextsage.parsing import ParsingOptions, default_patterns
from contextsage.policies import BalancedPolicy, MaximumCompressionPolicy, MaximumPreservationPolicy
from contextsage.provenance import create_agxai_runtime
from contextsage.sinks import CompositeEventSink, LoggingEventSink, OpenTelemetryEventSink
from contextsage.tokens import TokenizerTokenCounter

try:
    __version__ = version("contextsage")
except PackageNotFoundError:  # pragma: no cover - only when imported from a source tree
    __version__ = "0.0.0"

# A library must not configure logging; the application decides where records go.
logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    "DEFAULT_IDENTIFIER_PATTERNS",
    "DEFAULT_SUMMARY_PROMPT",
    "BalancedPolicy",
    "CompositeEventSink",
    "ConfigurationError",
    "ContextSageError",
    "ContextSummarizer",
    "EventSink",
    "Fact",
    "FrameworkAdapter",
    "JSONCompaction",
    "LoggingEventSink",
    "MaximumCompressionPolicy",
    "MaximumPreservationPolicy",
    "Message",
    "OpenTelemetryEventSink",
    "ParsingOptions",
    "PreservationPolicy",
    "PreservationThresholds",
    "RecoveryStatus",
    "Role",
    "SummarizationEvent",
    "SummarizationResult",
    "SummaryLineage",
    "TokenCounter",
    "TokenizerTokenCounter",
    "ToolCall",
    "ValidationStatus",
    "__version__",
    "create_agxai_runtime",
    "default_patterns",
]
