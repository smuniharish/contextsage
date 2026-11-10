# Examples

The repository's [examples README](https://github.com/smuniharish/contextsage/blob/master/examples/README.md) lists setup,
dependencies and commands. Offline examples use scripted models, run without
provider credentials, and are checked against recorded output.

## Core and framework integration

| Example | Demonstrates |
| --- | --- |
| [Quickstart](../examples/quickstart.py) | Async framework-neutral engine, facts, compaction and events |
| [Custom framework](../examples/custom_framework.py) | `FrameworkAdapter` implementation and lineage between generations |
| [LangChain agent](../examples/langchain_agent.py) | Optional LangChain integration |
| [Downstream customization](../examples/downstream_customization.py) | parsefabric and agxai component customization |

## Summarization behavior

| Example | Demonstrates |
| --- | --- |
| [Large tool output](../examples/large_tool_output.py) | Compaction of mixed structured content |
| [Preservation](../examples/preservation.py) | Required facts and conflicts |
| [Policies](../examples/policies.py) | Built-in and custom preservation policies |
| [Recovery](../examples/recovery.py) | Safe trimming after model failure |
| [Custom parsing](../examples/custom_parsing.py) | A custom parsefabric parser route |
| [Provenance](../examples/provenance.py) | Lineage queries and deletion |
| [Observability](../examples/observability.py) | Custom events and OpenTelemetry metrics |
| [Prometheus](../examples/observability_prometheus.py) | A custom Prometheus event sink |

## Service-backed and live examples

[PostgreSQL provenance](../examples/postgres_store.py) demonstrates an agxai
store implementation. [OpenTelemetry export](../examples/otel_export.py)
sends traces and metrics through a collector to Jaeger.

The live examples use an OpenAI-compatible provider and require
`CONTEXTSAGE_LLM_API_KEY`: [LangChain agent](../examples/live_agent.py),
[Deep Agent](../examples/deep_agent.py), and
[LangGraph swarm](../examples/swarm.py).
