# Performance

The cost of a summarization depends on history size, parser configuration,
token counting, execution backend and summary-model latency. The benchmark
uses the framework-neutral asynchronous engine and a scripted model, so it
measures local processing without provider latency:

```powershell
uv run python benchmarks\bench_middleware.py
uv run python benchmarks\bench_middleware.py --smoke
```

The smoke mode verifies each case without making a real model call. Run the
full benchmark on the target hardware before choosing concurrency and
trigger thresholds; do not treat measurements from another machine as a
service-level guarantee.

## What contributes to latency

- **Token counting:** runs before the trigger decision. Supply a
  `TokenCounter` backed by the model's tokenizer when exact counts are
  required.
- **Parsing and analysis:** runs when a rewrite is triggered. It uses
  parsefabric's `ExecutionBackend`; the default backend keeps CPU work off the
  event loop.
- **Model and persistence calls:** summary generation and agxai provenance
  writes are awaited and depend on your configured providers and storage.
- **Event delivery:** custom event sinks run asynchronously; buffer or
  enqueue network exports if they must not add provider latency.

## Tuning

- Use `ParsingOptions(code_detector=None)` when code recognition is not
  needed.
- Adjust `max_concurrency` for the parser mix and available resources.
- Tune the trigger to avoid repeatedly analyzing the full history too early.
- Prefer a model-specific `TokenCounter` when approximate counts are
  insufficient.
- Choose `keep` and summary-model input limits based on the actual task
  context.

`SummarizationEvent` reports input, prepared and output token counts,
compression ratio and latency for production measurements.
