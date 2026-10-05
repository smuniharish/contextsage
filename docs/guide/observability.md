# Observability

Each time ContextSage rewrites the history, it emits one `SummarizationEvent`.
The event is logged to the `contextsage` logger at `INFO` level, under the
`contextsage` attribute of the log record, and passed to your
`observability_hook`. Events hold counts, ratios and statuses only: never
message content, tool output or credentials.

## The event

| Field | Meaning |
| --- | --- |
| `summary_id` | ID of the summary message that now opens the history; `None` when only compaction ran |
| `generation` | 1 for a first summary, 2 for a summary of a summary, and so on; 0 without a summary |
| `thread_id` | The LangGraph thread, when the agent runs with a checkpointer |
| `trigger_reason` | Which trigger condition fired, such as `66 tokens >= 50 and 6 messages >= 6` |
| `input_messages`, `input_tokens` | The history before the rewrite |
| `available_tokens`, `overflow_tokens` | The input budget, and how far the history was over the trigger or budget |
| `prepared_tokens` | Tokens after compaction, before the summary |
| `output_messages`, `output_tokens` | The rewritten history |
| `compression_ratio` | `output_tokens / input_tokens` |
| `compacted_units` | Content units that compaction rewrote |
| `must_preserve_units`, `must_preserve_facts` | How much content was must-preserve, and how many facts validation required |
| `content_kinds` | Content units per kind, such as `{"json": 1, "log": 2, "text": 4}` |
| `validation_status`, `recovery_status` | See [Validation and recovery](validation-recovery.md#statuses) |
| `latency_ms` | Time spent in the middleware, including the summary call |

`SummarizationEvent.as_dict()` returns the event as a JSON-compatible
dictionary.

## Logs and a hook

```python
--8<--
examples/observability.py
--8<--
```

Output:

```text
--8<-- "examples/expected/observability.txt"
```

The hook runs in the agent's thread or event loop, right after the history is
rewritten. Keep it fast, and hand slow work such as network exports to a
queue. An exception raised by the hook is logged and never interrupts the
agent.

## Log messages

The package installs a `NullHandler` on the `contextsage` logger, so it is
silent until you configure logging:

| Level | Message |
| --- | --- |
| `INFO` | `contextsage summarization`, with the event attached |
| `WARNING` | The summary model failed and the history was trimmed instead |
| `WARNING` | A tool result lost its tool call after summarization |
| `WARNING` | A provenance link could not be written, or the hook raised |
| `WARNING` | Compacting one content unit failed; the unit was kept as it was |
| `ERROR` | The history could not be analyzed and was summarized unanalyzed |

## Metrics

Export the event as metrics from the hook. Label metrics with the
low-cardinality statuses only, never with IDs. With
[prometheus-client](https://pypi.org/project/prometheus-client/):

```python
--8<--
examples/observability_prometheus.py
--8<--
```

Output:

```text
--8<-- "examples/expected/observability_prometheus.txt"
```

[`observability_prometheus.yml`](https://github.com/smuniharish/contextsage/blob/master/examples/observability_prometheus.yml)
is a matching Prometheus scrape configuration. With the OpenTelemetry metrics
API, the hook looks like this:

```python
from opentelemetry import metrics

from contextsage import IntelligentSummarizationMiddleware, SummarizationEvent

meter = metrics.get_meter("contextsage")
summarizations = meter.create_counter("contextsage.summarizations")
compression = meter.create_histogram("contextsage.compression_ratio")


def export(event: SummarizationEvent) -> None:
    attributes = {
        "validation_status": event.validation_status,
        "recovery_status": event.recovery_status,
    }
    summarizations.add(1, attributes)
    compression.record(event.compression_ratio, attributes)


middleware = IntelligentSummarizationMiddleware(
    model="openai:gpt-5-mini", observability_hook=export
)
```

## Tracing and streaming

The summary call is an ordinary LangChain model call, so LangSmith and other
LangChain tracers record it within the agent run. When you stream an agent
with `stream_events(version="v3")`, the summary model's tokens are kept out of
the agent's message stream, as with LangChain's own summarization.
