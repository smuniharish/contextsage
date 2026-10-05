"""ContextSage: information-aware context summarization for LangChain agents.

ContextSage is a drop-in replacement for LangChain's ``SummarizationMiddleware``.
It parses heterogeneous agent context with parsefabric, keeps what matters,
compacts what is repetitive, lets LangChain write the summary, verifies that
nothing important was lost, and records provenance with langgraph-xai.

    from contextsage import IntelligentSummarizationMiddleware
"""

import logging

from contextsage._pipeline.signals import DEFAULT_IDENTIFIER_PATTERNS
from contextsage.errors import ConfigurationError, ContextSageError
from contextsage.events import RecoveryStatus, SummarizationEvent, ValidationStatus
from contextsage.middleware import IntelligentSummarizationMiddleware

__version__ = "1.0.0"

__all__ = [
    "DEFAULT_IDENTIFIER_PATTERNS",
    "ConfigurationError",
    "ContextSageError",
    "IntelligentSummarizationMiddleware",
    "RecoveryStatus",
    "SummarizationEvent",
    "ValidationStatus",
    "__version__",
]

logging.getLogger("contextsage").addHandler(logging.NullHandler())
