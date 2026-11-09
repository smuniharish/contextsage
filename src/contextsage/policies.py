"""The built-in preservation policies."""

from __future__ import annotations

from typing import override

from contextsage.contracts import JSONCompaction, PreservationPolicy, PreservationThresholds

__all__ = ["BalancedPolicy", "MaximumCompressionPolicy", "MaximumPreservationPolicy"]


class MaximumPreservationPolicy(PreservationPolicy):
    """Keep as much as possible; JSON is only minified."""

    @property
    @override
    def thresholds(self) -> PreservationThresholds:
        return PreservationThresholds(must=0.60, should=0.30, error_must=0.45)

    @property
    @override
    def json_compaction(self) -> JSONCompaction:
        return JSONCompaction.MINIFY


class BalancedPolicy(PreservationPolicy):
    """The default: lossless JSON compaction and moderate thresholds."""

    @property
    @override
    def thresholds(self) -> PreservationThresholds:
        return PreservationThresholds(must=0.75, should=0.45, error_must=0.60)

    @property
    @override
    def json_compaction(self) -> JSONCompaction:
        return JSONCompaction.COLLAPSE_RUNS


class MaximumCompressionPolicy(PreservationPolicy):
    """Compact aggressively; long JSON lists of compressible content are sampled."""

    @property
    @override
    def thresholds(self) -> PreservationThresholds:
        return PreservationThresholds(must=0.90, should=0.65, error_must=0.80)

    @property
    @override
    def json_compaction(self) -> JSONCompaction:
        return JSONCompaction.SAMPLE
