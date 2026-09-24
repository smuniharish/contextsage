"""ContextIQ: intelligent, production-grade context summarization for LangGraph agents.

ContextIQ is a narrowly-focused enhancement layer over LangGraph/LangChain's
built-in ``SummarizationMiddleware``. It analyzes heterogeneous agent context
(mixed natural language, JSON, logs, errors, tables, code) to decide *what*
should be preserved, compressed, or left untouched, then delegates the
actual LLM-based semantic summarization to LangGraph itself.

The public surface of this package is intentionally small — a single class:

    from contextiq import IntelligentSummarizationMiddleware

See ``docs/`` for the full architecture, or the module docstrings under
``contextiq.middleware``, ``contextiq.planning``, ``contextiq.validation``,
etc. for internal implementation details.
"""

from contextiq.middleware.summarization import IntelligentSummarizationMiddleware

__all__ = ["IntelligentSummarizationMiddleware", "__version__"]

__version__ = "0.1.0"
