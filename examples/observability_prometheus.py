"""Real external telemetry integration: ContextIQ -> Prometheus -> Grafana.

`docs/observability.md` documents `observability_hook=` as a plain callable
that receives a `SummarizationEvent`. This example proves that claim against
a real external system rather than a mock: it builds a custom hook that
records every field of `SummarizationEvent` as Prometheus metrics, serves
them on `/metrics`, and drives several real-LLM summarizations (of varying
sizes/outcomes) so the metrics have real, varied values to scrape.

Run with:

    python examples/observability_prometheus.py

Requires a real API key (see examples/_llm.py) and the `examples` extra:

    pip install -e ".[examples]"

Then, separately, point a real Prometheus + Grafana stack at this process
(see `examples/observability_prometheus.yml` for a ready-to-use Prometheus
scrape config, and the podman commands in that file's header comment) to
see the metrics graphed. This script keeps its metrics endpoint alive for
`OBSERVABILITY_DEMO_SECONDS` seconds (default 120) after the last
summarization so a scrape has time to land.
"""

from __future__ import annotations

import os
import time

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from prometheus_client import Counter, Histogram, start_http_server

from _llm import build_demo_model
from contextiq import IntelligentSummarizationMiddleware
from contextiq.observability.events import SummarizationEvent

# One metric per SummarizationEvent field that varies meaningfully across
# operations. Labels use only the low-cardinality status/reason strings
# documented in docs/observability.md -- never raw content.
SUMMARIZATIONS_TOTAL = Counter(
    "contextiq_summarizations_total",
    "Number of IntelligentSummarizationMiddleware operations, by outcome.",
    labelnames=("validation_status", "recovery_status", "fallback_used"),
)
INPUT_TOKENS = Histogram(
    "contextiq_input_tokens",
    "Observed input token count *before* summarization (at trigger time).",
    buckets=(50, 100, 250, 500, 1000, 2500, 5000, 10_000),
)
SUMMARY_TOKENS = Histogram(
    "contextiq_summary_tokens",
    "Token count of the produced summary *after* summarization -- graph "
    "alongside contextiq_input_tokens to see the actual before/after "
    "reduction, not just the derived compression_ratio.",
    buckets=(50, 100, 250, 500, 1000, 2500, 5000, 10_000),
)
COMPRESSION_RATIO = Histogram(
    "contextiq_compression_ratio",
    "summary_tokens / input_tokens for each summarization operation.",
    buckets=(0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0),
)
LATENCY_MS = Histogram(
    "contextiq_latency_ms",
    "End-to-end before_model latency in milliseconds.",
    buckets=(50, 100, 250, 500, 1000, 2500, 5000, 10_000, 30_000),
)


def prometheus_observability_hook(event: SummarizationEvent) -> None:
    """A real `ObservabilityHook`: records one `SummarizationEvent` as metrics."""
    SUMMARIZATIONS_TOTAL.labels(
        validation_status=event.validation_status,
        recovery_status=event.recovery_status,
        fallback_used=str(event.fallback_used),
    ).inc()
    INPUT_TOKENS.observe(event.input_tokens)
    SUMMARY_TOKENS.observe(event.summary_tokens)
    COMPRESSION_RATIO.observe(event.compression_ratio)
    LATENCY_MS.observe(event.latency_ms)
    print(
        f"[observability] trigger={event.trigger_reason!r} "
        f"input_tokens={event.input_tokens} summary_tokens={event.summary_tokens} "
        f"compression_ratio={event.compression_ratio:.3f} "
        f"validation={event.validation_status} recovery={event.recovery_status} "
        f"latency_ms={event.latency_ms:.1f}"
    )


def _conversation(size: str) -> list:
    """Build a conversation that reliably triggers summarization at size `size`."""
    base = [
        HumanMessage(content="Please process the order for customer 123.", id="h1"),
        AIMessage(
            content="",
            id="a1",
            tool_calls=[{"id": "call-1", "name": "lookup_order", "args": {"customer": 123}}],
        ),
        ToolMessage(
            content=(
                "status=processing transaction_id=TX-991\n"
                + ("INFO heartbeat ok\n" * (40 if size == "large" else 5))
                + "ERROR root cause: connection pool exhaustion\n"
            ),
            tool_call_id="call-1",
            id="t1",
        ),
        HumanMessage(content="Any update on TX-991?", id="h2"),
    ]
    if size == "large":
        base.append(
            HumanMessage(
                content="Also double check the customer's shipping address is still 456 Oak St.",
                id="h3",
            )
        )
    return base


def main() -> None:
    model = build_demo_model()

    print("Starting Prometheus metrics endpoint on http://localhost:9109/metrics ...")
    start_http_server(9109)

    for size, trigger_tokens in (("small", 400), ("large", 60)):
        middleware = IntelligentSummarizationMiddleware(
            model=model,
            trigger=("tokens", trigger_tokens),
            keep=("messages", 1),
            observability_hook=prometheus_observability_hook,
        )
        result = middleware.before_model({"messages": _conversation(size)}, None)
        if result is None:
            print(f"[{size}] no summarization triggered at threshold={trigger_tokens}")

    demo_seconds = int(os.environ.get("OBSERVABILITY_DEMO_SECONDS", "120"))
    print(
        f"\nMetrics are live at http://localhost:9109/metrics for {demo_seconds}s "
        "-- point Prometheus at this process now (see examples/observability_prometheus.yml)."
    )
    time.sleep(demo_seconds)


if __name__ == "__main__":
    main()
