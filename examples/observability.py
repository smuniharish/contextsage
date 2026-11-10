"""Observe every summarization through logging, OpenTelemetry and your own sink.

Run: python examples/observability.py

Each rewrite emits one content-free `SummarizationEvent` to the summarizer's
`EventSink`. Here a `CompositeEventSink` delivers it to three sinks:

- `LoggingEventSink` logs it to the ``contextsage`` logger at INFO level, with
  the event under the ``contextsage`` attribute of the log record.
- `OpenTelemetryEventSink` records it as OpenTelemetry metrics; an in-memory
  reader stands in for an exporter (see ``otel_export.py`` for OTLP).
- ``AlertSink``, a custom `EventSink`, flags rewrites that had to restate facts.

No sink ever receives message content.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import override

from _shared import ScriptedModel
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from contextsage import (
    CompositeEventSink,
    ContextSummarizer,
    EventSink,
    LoggingEventSink,
    Message,
    OpenTelemetryEventSink,
    SummarizationEvent,
    ToolCall,
)

VOLATILE = {"summary_id", "latency_ms"}


class JSONEventHandler(logging.Handler):
    """Print the structured event attached to ContextSage log records."""

    @override
    def emit(self, record: logging.LogRecord) -> None:
        event = {
            key: value
            for key, value in getattr(record, "contextsage", {}).items()
            if key not in VOLATILE
        }
        print(f"log record '{record.getMessage()}':")
        print(json.dumps(event, indent=2))


class AlertSink(EventSink):
    """Flag rewrites that needed facts restated."""

    @override
    async def emit(self, event: SummarizationEvent) -> None:
        if event.recovery_status != "none_needed":
            print(f"alert: recovery '{event.recovery_status}' after {event.trigger_reason}")


BILLING_LOG = "".join(
    f"2026-10-04T07:{index // 60:02d}:{index % 60:02d}Z INFO billing-worker charge ok\n"
    for index in range(120)
)
HISTORY = [
    Message("user", "Invoice INV-2048 for customer 77 was charged twice."),
    Message("assistant", "", tool_calls=(ToolCall("c1", "billing_log", {}),)),
    Message(
        "tool",
        BILLING_LOG + "2026-10-04T09:00:00Z ERROR duplicate charge for INV-2048\n",
        tool_call_id="c1",
    ),
    Message("assistant", "The billing log shows a duplicate charge for INV-2048."),
    Message("user", "Refund the duplicate."),
    Message("assistant", "Refund issued."),
]


async def main() -> None:
    logger = logging.getLogger("contextsage.example")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(JSONEventHandler())
    reader = InMemoryMetricReader()
    meter = MeterProvider(metric_readers=[reader]).get_meter("contextsage")
    sink = CompositeEventSink(
        [LoggingEventSink(logger), OpenTelemetryEventSink(meter), AlertSink()]
    )

    async with ContextSummarizer(
        ScriptedModel("Discussed the invoice."),
        trigger=("messages", 6),
        keep=("messages", 2),
        sink=sink,
    ) as summarizer:
        await summarizer.summarize(HISTORY)

    print()
    print("OpenTelemetry metrics:")
    data = reader.get_metrics_data()
    if data is None:
        raise SystemExit("No metrics were recorded.")
    attributes: dict[str, object] = {}
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name == "contextsage.duration":
                    continue
                point = next(iter(metric.data.data_points))
                attributes = dict(point.attributes or {})
                value = getattr(point, "value", None)
                if value is None:
                    value = f"sum={getattr(point, 'sum', 0)}"
                print(f"  {metric.name}: {value}")
    print(f"  attributes: {attributes}")


if __name__ == "__main__":
    asyncio.run(main())
