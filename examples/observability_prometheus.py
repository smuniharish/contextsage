"""Export ContextSage events as Prometheus metrics with a custom `EventSink`.

Run: python examples/observability_prometheus.py

Requires prometheus-client (installed with the ``examples`` dependency group).
The script serves metrics on http://localhost:9109/metrics, runs a few
summarizations, then keeps serving for ``OBSERVABILITY_DEMO_SECONDS`` seconds
(default 60) so a Prometheus server can scrape it. See
``examples/observability_prometheus.yml`` for a scrape configuration.
"""

from __future__ import annotations

import asyncio
import os
from typing import override

from _shared import ScriptedModel
from prometheus_client import CollectorRegistry, Counter, Histogram, start_http_server

from contextsage import ContextSummarizer, EventSink, Message, SummarizationEvent, ToolCall

TOKEN_BUCKETS = (250, 500, 1_000, 2_500, 5_000, 10_000, 25_000, 100_000)


class PrometheusEventSink(EventSink):
    """Record every event as Prometheus metrics, labelled by outcome."""

    def __init__(self, registry: CollectorRegistry) -> None:
        labels = ("validation_status", "recovery_status", "policy")
        self._summarizations = Counter(
            "contextsage_summarizations",
            "Rewritten histories by outcome.",
            labels,
            registry=registry,
        )
        self._input_tokens = Histogram(
            "contextsage_input_tokens",
            "Tokens in the history before summarization.",
            buckets=TOKEN_BUCKETS,
            registry=registry,
        )
        self._output_tokens = Histogram(
            "contextsage_output_tokens",
            "Tokens in the history after summarization.",
            buckets=TOKEN_BUCKETS,
            registry=registry,
        )
        self._compression = Histogram(
            "contextsage_compression_ratio",
            "Output tokens divided by input tokens.",
            buckets=(0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5),
            registry=registry,
        )
        self._latency = Histogram(
            "contextsage_latency_ms",
            "Time spent summarizing, in milliseconds.",
            buckets=(10, 50, 100, 250, 500, 1_000, 2_500, 10_000, 30_000),
            registry=registry,
        )

    @override
    async def emit(self, event: SummarizationEvent) -> None:
        self._summarizations.labels(
            event.validation_status, event.recovery_status, event.policy
        ).inc()
        self._input_tokens.observe(event.input_tokens)
        self._output_tokens.observe(event.output_tokens)
        self._compression.observe(event.compression_ratio)
        self._latency.observe(event.latency_ms)
        print(
            f"{event.input_tokens} -> {event.output_tokens} tokens, "
            f"validation={event.validation_status}, recovery={event.recovery_status}"
        )


def history(size: int) -> list[Message]:
    """A conversation whose tool result holds ``size`` routine log lines."""
    log = "".join(
        f"2026-10-04T10:{index // 60:02d}:{index % 60:02d}Z INFO sync batch done\n"
        for index in range(size)
    )
    return [
        Message("user", "Why did the nightly sync for tenant T-310 fail?"),
        Message("assistant", "", tool_calls=(ToolCall("c1", "sync_logs", {}),)),
        Message(
            "tool", log + "2026-10-04T11:00:00Z ERROR sync aborted for T-310\n", tool_call_id="c1"
        ),
        Message("assistant", "The sync for T-310 aborted."),
        Message("user", "What should we do?"),
    ]


async def main() -> None:
    registry = CollectorRegistry()
    server, thread = start_http_server(9109, registry=registry)
    print("Serving metrics on http://localhost:9109/metrics")
    try:
        async with ContextSummarizer(
            ScriptedModel("The nightly sync for tenant T-310 aborted."),
            trigger=("tokens", 500),
            keep=("messages", 2),
            sink=PrometheusEventSink(registry),
        ) as summarizer:
            for size in (50, 400, 1_500):
                await summarizer.summarize(history(size))
        await asyncio.sleep(int(os.environ.get("OBSERVABILITY_DEMO_SECONDS", "60")))
    finally:
        server.shutdown()
        thread.join()


if __name__ == "__main__":
    asyncio.run(main())
