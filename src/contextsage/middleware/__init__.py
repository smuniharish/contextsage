"""Public middleware package.

Exposes :class:`~contextsage.middleware.summarization.IntelligentSummarizationMiddleware`,
re-exported at the top level as ``contextsage.IntelligentSummarizationMiddleware``.
"""

from contextsage.middleware.summarization import IntelligentSummarizationMiddleware

__all__ = ["IntelligentSummarizationMiddleware"]
