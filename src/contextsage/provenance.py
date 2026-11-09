"""Provenance through agxai: summary lineage links and runtime construction."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agxai import (
    AttributionEngine,
    CapturePolicy,
    ExplanationEngine,
    ObservabilityProvider,
    PolicyProvider,
    ProvenanceStore,
    XAIRuntime,
)

from contextsage.errors import ConfigurationError

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from agxai import Registry, XAIConfig, XAIPlugin

__all__ = ["create_agxai_runtime"]


def create_agxai_runtime(
    *,
    config: XAIConfig | None = None,
    registry: Registry | None = None,
    application_id: str = "contextsage",
    tenant_id: str = "default",
    graph_id: str = "agent",
    plugins: Sequence[XAIPlugin] = (),
    custom_state_capture: Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]]
    | None = None,
    store: ProvenanceStore | None = None,
    observability: ObservabilityProvider | None = None,
    attribution: AttributionEngine | None = None,
    explanation: ExplanationEngine | None = None,
    policy: PolicyProvider | None = None,
    capture_policy: CapturePolicy | None = None,
) -> XAIRuntime:
    """Build an ``agxai.XAIRuntime`` with any of its components replaced.

    Every agxai extension point can be supplied here: the runtime settings and
    identity, plugins, custom state capture, and each registered capability.
    A capability left as ``None`` keeps the provider already in ``registry``,
    or agxai's default. Pass the runtime to
    ``ContextSummarizer(runtime=...)``; share it with your agent's agxai
    instrumentation so summaries appear in the same provenance graph.

    Args:
        config: ``agxai.XAIConfig`` capture, failure and concurrency settings.
        registry: An ``agxai.Registry`` to share providers between runtimes.
        application_id: Application identifier of recorded links and runs.
        tenant_id: Tenant identifier of recorded links and runs.
        graph_id: Graph identifier of recorded links and runs.
        plugins: ``agxai.XAIPlugin`` instances that receive semantic artifacts.
        custom_state_capture: The state capture function agxai requires for
            ``CaptureMode.CUSTOM``.
        store: The ``agxai.ProvenanceStore`` that records summary lineage.
        observability: The ``agxai.ObservabilityProvider`` canonical events go to.
        attribution: The ``agxai.AttributionEngine`` that scores decisions.
        explanation: The ``agxai.ExplanationEngine`` that renders explanations.
        policy: The ``agxai.PolicyProvider`` that filters explanations by audience.
        capture_policy: The ``agxai.CapturePolicy`` that gates captured events.

    Returns:
        The configured runtime.

    Raises:
        ConfigurationError: If a component is not an instance of its agxai
            base class, or agxai rejects the configuration.
    """
    capabilities: tuple[tuple[str, type[Any], object | None], ...] = (
        ("store", ProvenanceStore, store),
        ("observability", ObservabilityProvider, observability),
        ("attribution", AttributionEngine, attribution),
        ("explanation", ExplanationEngine, explanation),
        ("policy", PolicyProvider, policy),
        ("capture_policy", CapturePolicy, capture_policy),
    )
    for name, capability, provider in capabilities:
        if provider is not None and not isinstance(provider, capability):
            raise ConfigurationError(
                f"{name} must be an agxai.{capability.__name__}, not {type(provider).__name__}"
            )
    try:
        runtime = XAIRuntime(
            config,
            registry,
            application_id=application_id,
            tenant_id=tenant_id,
            graph_id=graph_id,
            plugins=tuple(plugins),
            custom_state_capture=custom_state_capture,
        )
    except (TypeError, ValueError) as error:
        raise ConfigurationError(str(error)) from error
    for _, capability, provider in capabilities:
        if provider is not None:
            runtime.register(capability, provider)
    return runtime
