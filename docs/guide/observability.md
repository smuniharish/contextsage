# Observability

Every rewritten history produces a content-free `SummarizationEvent` with
message and token counts, compression ratio, content kinds, preserved facts,
validation and recovery statuses, policy and latency. It does not contain
message text, tool output or credentials.

## Event sinks

By default, `LoggingEventSink` writes structured events to the `contextsage`
logger. Supply an `EventSink` ABC implementation to send events elsewhere:

```python
async def summarize_with_sink(model, my_sink, messages):
    async with ContextSummarizer(model, sink=my_sink) as summarizer:
        result = await summarizer.summarize(messages)
    return result
```

`EventSink.emit` is asynchronous. Optional `flush` and `close` methods can
release or drain resources; the engine logs sink errors rather than failing an
agent turn. `CompositeEventSink` forwards to multiple sinks.

## OpenTelemetry

`OpenTelemetryEventSink` records the event through the OpenTelemetry API.
Install `contextsage[otel]` for the SDK and OTLP exporter, then configure the
provider/exporter in your application. ContextSage also creates spans for
summarization, analysis, model calls, validation and provenance.

The [OpenTelemetry example](../../examples/otel_export.py) sends traces and
metrics through a collector to Jaeger. The
[Prometheus example](../../examples/observability_prometheus.py) shows a
custom event sink.

## Parse lifecycle events

`ParsingOptions.sink` is separate: it receives parsefabric parsing and
execution lifecycle events. Use it when you need visibility into parser
operations as well as summary outcomes.
