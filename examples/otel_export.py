"""Export ContextSage traces and metrics through an OTLP HTTP collector to Jaeger.

Start Jaeger and the collector using the commands in ``examples/README.md``,
then run this script. It uses a scripted summary model, so no LLM credentials
are needed. Open Jaeger at http://localhost:16686 and select the
``contextsage-example`` service.

``OTEL_EXPORTER_OTLP_ENDPOINT`` may override the collector URL; its default is
``http://localhost:4318``. The collector forwards traces to Jaeger with OTLP
gRPC and writes both signals to its debug exporter.
"""

from __future__ import annotations

import asyncio
import os

from _shared import ScriptedModel
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from contextsage import ContextSummarizer, Message, OpenTelemetryEventSink, ToolCall


async def main() -> None:
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318").rstrip("/")
    resource = Resource.create({"service.name": "contextsage-example"})

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        SimpleSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces"))
    )
    trace.set_tracer_provider(tracer_provider)

    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics"),
        export_interval_millis=1_000,
        export_timeout_millis=5_000,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    history = [
        Message("user", "Investigate incident INC-9931."),
        Message("assistant", "", tool_calls=(ToolCall("c1", "incident_report", {}),)),
        Message(
            "tool",
            "Incident INC-9931: connection pool exhausted while settling TX-991.\n"
            + "".join(f"INFO payments-worker-{index % 4} queue healthy\n" for index in range(300)),
            tool_call_id="c1",
        ),
        Message("assistant", "The payments connection pool is exhausted."),
        Message("user", "What should we do next?"),
    ]

    try:
        async with ContextSummarizer(
            ScriptedModel(
                "The payments outage INC-9931 is caused by a saturated connection pool; "
                "transaction TX-991 failed."
            ),
            trigger=("tokens", 500),
            keep=("messages", 2),
            sink=OpenTelemetryEventSink(),
        ) as summarizer:
            result = await summarizer.summarize(history, thread_id="incident-9931")
        if result is None:
            raise SystemExit("The history did not trigger summarization.")
    finally:
        tracer_provider.force_flush()
        meter_provider.force_flush()
        tracer_provider.shutdown()
        meter_provider.shutdown()

    print(
        f"Exported trace and metrics for incident-9931: "
        f"{result.event.input_tokens} -> {result.event.output_tokens} tokens."
    )
    print("Inspect the trace in Jaeger at http://localhost:16686.")


if __name__ == "__main__":
    asyncio.run(main())
