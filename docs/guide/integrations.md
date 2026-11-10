# Framework and package integrations

The ContextSage core accepts `Message` objects and a parsefabric
`LanguageModel`. It has no framework dependency. An adapter translates a
framework's message types at the boundary, leaving summarization behavior
identical across integrations.

## Custom frameworks

Implement `FrameworkAdapter[NativeT]` as an ABC. `to_message` preserves the
framework object in `Message.native`; `from_message` returns or updates native
messages where possible and creates framework messages for summaries. Override
`propagated_errors` for framework control-flow exceptions.

<!-- docs-test: skip -->
```python
class MyAdapter(FrameworkAdapter[NativeMessage]):
    def to_message(self, native: NativeMessage) -> Message: ...

    def from_message(self, message: Message) -> NativeMessage: ...
```

Convert a full history with `adapter.to_messages`, pass it to
`ContextSummarizer.summarize`, and convert `result.messages` back with
`adapter.from_messages`. Store `Message.lineage` in framework metadata or
checkpoint state so provenance survives later turns. See the
[custom framework example](../../examples/custom_framework.py).

## LangChain

Install `contextsage[langchain]` to use the optional integration:

<!-- docs-test: skip -->
```python
from contextsage.integrations.langchain import IntelligentSummarizationMiddleware

agent = create_agent(
    model=agent_model,
    tools=tools,
    middleware=[
        IntelligentSummarizationMiddleware(
            summary_model,
            trigger=("tokens", 100_000),
            keep=("messages", 20),
        )
    ],
)
```

The integration provides:

- `LangChainAdapter` for native LangChain messages and lineage metadata.
- `LangChainSummaryModel` for asynchronous chat-model calls.
- `LangChainTokenCounter` using LangChain's token-counting function.
- `IntelligentSummarizationMiddleware` for LangChain agents and Deep Agents.

`LINEAGE_KEY` identifies the lineage stored in summary-message metadata.
Access the engine through `middleware.summarizer`; use `alineage` and
`adelete_lineage` for asynchronous provenance operations.

## Downstream customization

ContextSage intentionally forwards its dependency extension points.

### parsefabric

Use `ParsingOptions` to supply all parser-related customization:

- `LanguageModel` for summary generation.
- `Tokenizer` through `TokenizerTokenCounter`.
- `Pattern` objects and parser routes, either direct or registry-resolved.
- Fenced-code parsers and code detector.
- JSON codec.
- Parse/execution lifecycle `ObservabilitySink`.
- CPU/I/O `ExecutionBackend` and message-level concurrency.

Each parsefabric component follows the dependency's ABC. See
[content parsing](content-parsing.md) and
[downstream customization](../../examples/downstream_customization.py).

### agxai

`create_agxai_runtime` accepts:

- `XAIConfig` and `Registry`.
- Application, tenant and graph IDs.
- `XAIPlugin` instances and custom state capture.
- `ProvenanceStore`.
- `ObservabilityProvider`, `AttributionEngine`, `ExplanationEngine`, and
  `PolicyProvider`.
- `CapturePolicy`.

The helper validates supplied components and registers them with an
`XAIRuntime`. Use the same runtime with agent instrumentation when summaries
should appear in the same graph.

### ContextSage and telemetry

ContextSage defines ABCs for `FrameworkAdapter`, `TokenCounter`,
`PreservationPolicy` and `EventSink`. Its event sinks include structured
logging, composite delivery and OpenTelemetry. Implement an `EventSink` for
another telemetry backend.

## Package and extra inventory

| Package | Install scope | Role |
| --- | --- | --- |
| `parsefabric` | Core dependency | Message parsing, language-model and tokenizer ABCs, parser and execution extension points |
| `agxai` | Core dependency | Runtime, provenance storage and registered capabilities |
| `opentelemetry-api` | Core dependency | Tracing API used by ContextSage |
| `langchain`, `langchain-core`, `langgraph` | `contextsage[langchain]` | Optional framework integration |
| `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http` | `contextsage[otel]` | Optional OpenTelemetry export |
| `deepagents`, `langchain-openai`, `langgraph-swarm`, `prometheus-client`, `psycopg`, `python-dotenv`, `sqlglot` | Development `examples` group | Runnable demos and service-backed verification; not runtime requirements |

Install `contextsage[all]` to combine both optional extras. The package does
not require unrelated logging or storage frameworks; choose the providers
that fit your application.
