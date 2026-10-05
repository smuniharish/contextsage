"""Export ContextSage events as Prometheus metrics.

Run: python examples/observability_prometheus.py

Requires prometheus-client (installed with the ``examples`` dependency group).
The script serves metrics on http://localhost:9109/metrics, runs a few
summarizations, then keeps serving for ``OBSERVABILITY_DEMO_SECONDS`` seconds
(default 60) so a Prometheus server can scrape it. See
``examples/observability_prometheus.yml`` for a scrape configuration.
"""

import os
import time

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langgraph.runtime import Runtime
from prometheus_client import Counter, Histogram, start_http_server

from _models import scripted_model
from contextsage import IntelligentSummarizationMiddleware, SummarizationEvent

SUMMARIZATIONS = Counter(
    "contextsage_summarizations_total",
    "Summarizations by validation and recovery outcome.",
    labelnames=("validation_status", "recovery_status"),
)
INPUT_TOKENS = Histogram(
    "contextsage_input_tokens",
    "Tokens in the history before summarization.",
    buckets=(250, 500, 1_000, 2_500, 5_000, 10_000, 25_000, 100_000),
)
OUTPUT_TOKENS = Histogram(
    "contextsage_output_tokens",
    "Tokens in the history after summarization.",
    buckets=(250, 500, 1_000, 2_500, 5_000, 10_000, 25_000, 100_000),
)
COMPRESSION = Histogram(
    "contextsage_compression_ratio",
    "Output tokens divided by input tokens.",
    buckets=(0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5),
)
LATENCY = Histogram(
    "contextsage_latency_ms",
    "Time spent in the middleware, in milliseconds.",
    buckets=(10, 50, 100, 250, 500, 1_000, 2_500, 10_000, 30_000),
)


def record(event: SummarizationEvent) -> None:
    """Record one event; labels use only low-cardinality status values."""
    SUMMARIZATIONS.labels(event.validation_status, event.recovery_status).inc()
    INPUT_TOKENS.observe(event.input_tokens)
    OUTPUT_TOKENS.observe(event.output_tokens)
    COMPRESSION.observe(event.compression_ratio)
    LATENCY.observe(event.latency_ms)
    print(
        f"{event.input_tokens} -> {event.output_tokens} tokens, "
        f"validation={event.validation_status}, recovery={event.recovery_status}"
    )


def history(size: int) -> list[AnyMessage]:
    """A conversation whose tool result holds ``size`` routine log lines."""
    log = "".join(
        f"2026-10-04T10:{index // 60:02d}:{index % 60:02d}Z INFO sync batch done\n"
        for index in range(size)
    )
    return [
        HumanMessage("Why did the nightly sync for tenant T-310 fail?"),
        AIMessage("", tool_calls=[{"id": "c1", "name": "sync_logs", "args": {}}]),
        ToolMessage(
            log + "2026-10-04T11:00:00Z ERROR sync aborted for T-310\n",
            tool_call_id="c1",
        ),
        AIMessage("The sync for T-310 aborted."),
        HumanMessage("What should we do?"),
    ]


start_http_server(9109)
print("Serving metrics on http://localhost:9109/metrics")
for size in (50, 400, 1_500):
    middleware = IntelligentSummarizationMiddleware(
        model=scripted_model("The nightly sync for tenant T-310 aborted."),
        trigger=("tokens", 500),
        keep=("messages", 2),
        observability_hook=record,
    )
    middleware.before_model({"messages": history(size)}, Runtime())
time.sleep(int(os.environ.get("OBSERVABILITY_DEMO_SECONDS", "60")))
