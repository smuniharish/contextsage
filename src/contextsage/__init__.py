"""ContextSage: intelligent, production-grade context summarization for LangGraph agents.

ContextSage is a narrowly-focused enhancement layer over LangGraph/LangChain's
built-in ``SummarizationMiddleware``. It analyzes heterogeneous agent context
(mixed natural language, JSON, logs, errors, tables, code) to decide *what*
should be preserved, compressed, or left untouched, then delegates the
actual LLM-based semantic summarization to LangGraph itself.

The public surface of this package is intentionally small — a single class:

    from contextsage import IntelligentSummarizationMiddleware

See ``docs/`` for the full architecture, or the module docstrings under
``contextsage.middleware``, ``contextsage.planning``, ``contextsage.validation``,
etc. for internal implementation details.
"""

from contextsage.middleware.summarization import IntelligentSummarizationMiddleware

__all__ = ["IntelligentSummarizationMiddleware", "__version__"]

__version__ = "0.1.0"
