# Production checklist

## Model and budget

- Choose a summary model with an asynchronous client and configure its
  connection timeout and retry behavior in the provider adapter.
- Set `maximum_context_tokens`, `reserved_output_tokens` and
  `summarization_overhead_tokens` to the actual model and prompt budget.
- Choose a trigger that leaves room for the summary request and the agent's
  next response.
- Retain enough recent messages in `keep` for the active tool exchange.
- Add `identifier_patterns` for domain identifiers that must be recognized.
- Exercise the chosen `PreservationPolicy` against representative histories.

## Runtime and resources

- Use a persistent agxai `ProvenanceStore` when lineage must survive process
  restarts.
- Pass the same agxai runtime used by agent instrumentation when summaries
  should share its identity and provenance graph.
- Call `prepare()` during startup if code-detection resources must be
  available before requests are accepted.
- Close the summarizer with its async context manager. Close caller-owned
  runtimes, event sinks and parsefabric backends according to their owners'
  lifecycle.
- Lock the environment and install only the optional extras and provider
  packages the application uses.

## Monitoring

- Export `SummarizationEvent` through an `EventSink`; use the
  `OpenTelemetryEventSink` or implement a sink for your metrics system.
- Alert on `trimmed_fallback` when the summary model is failing and
  `failed_unrecovered` when tool-call structure needs investigation.
- Track compression ratio, latency, preserved fact counts and
  `failed_recovered` rates without using message content as metric labels.
- Route warnings and errors from the `contextsage` logger to the application
  log pipeline.

## Privacy and validation

- Choose a summary provider and agxai storage backend that satisfy your data
  handling requirements.
- Keep message content and credentials out of custom events and logs.
- Test realistic tool output, IDs, corrections, conflicts and model failures
  using scripted models before enabling live provider calls.

See [configuration](../guide/configuration.md),
[observability](../guide/observability.md) and
[security](security.md).
