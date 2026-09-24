"""Public middleware package.

Exposes :class:`~contextiq.middleware.summarization.IntelligentSummarizationMiddleware`,
re-exported at the top level as ``contextiq.IntelligentSummarizationMiddleware``.
"""

from contextiq.middleware.summarization import IntelligentSummarizationMiddleware

__all__ = ["IntelligentSummarizationMiddleware"]
