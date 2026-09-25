# Configuration and production decisions

All ContextSage configuration is passed to
`IntelligentSummarizationMiddleware`; it has no configuration file, command,
or registration API. The complete parameter table and defaults are
authoritative in
[Configuration - ContextSage](https://contextsage.readthedocs.io/en/latest/configuration/).

## Select configuration from evidence

| Decision | Use | Validate |
| --- | --- | --- |
| When to summarize | `trigger` or budget-driven `trigger=None` | Trigger/non-trigger behavior on representative messages. |
| Recent raw context to retain | `keep` | The tail still contains the conversation needed for the next model call. |
| Model budget | `maximum_context_tokens`, `reserved_output_tokens`, `safety_margin`, `summarization_overhead_tokens` | Available input budget and no context-window overflow. |
| Compression/preservation tradeoff | `policy` | Corrections, constraints, identifiers, root causes, and conflicting evidence survive. |
| Semantic summary input | `summary_prompt`, `trim_tokens_to_summarize` | Summary quality and size under real workload data. |
| Validation/recovery | `validation_enabled` | A deliberately incomplete summary is recovered as expected. |
| Telemetry | `observability_enabled`, `observability_hook` | Event fields, no raw-content leakage, and monitoring integration. |
| Provenance overhead | `provenance_enabled` | Whether the application's lineage requirement justifies it. |
| Tokenization/provider accuracy | `token_counter` | Counts against the configured model/provider. |
| Specialized structural format | `parsers` and, separately, classification-pattern overrides | Format detection and preservation behavior with a focused test. |

## Production defaults and observability

The default policy is `"balanced"`. `"maximum_preservation"` raises the
threshold for compression; `"maximum_compression"` can target
`SHOULD_PRESERVE` material, while mandatory preservation remains protected.
Choose a policy only after testing the application's actual data.

Validation and default logging observability are enabled by default. The
default hook emits aggregate `SummarizationEvent` data to the
`contextsage.observability` logger. Events do not include raw messages, tool
output, or API keys. The event fields and a Prometheus hook example are in
[Observability - ContextSage](https://contextsage.readthedocs.io/en/latest/observability/)
and the [Prometheus example](https://github.com/smuniharish/contextsage/blob/master/examples/observability_prometheus.py).

`langgraph-xai` provenance is a direct runtime dependency and is best effort:
failure to record provenance does not abort summarization. There is no normal
application setup required for its default in-memory behavior. Read
[Provenance - ContextSage](https://contextsage.readthedocs.io/en/latest/provenance/)
before relying on
provenance in a production architecture.

## Do not overconfigure

Start with `model`, an evidence-based `trigger`, and `keep`. Add budget
overrides only when automatic inference does not represent the configured
model. Add custom token counting or parsers only when an integration test
demonstrates the need. Do not use configuration as a substitute for
inspecting message shapes and middleware order.
