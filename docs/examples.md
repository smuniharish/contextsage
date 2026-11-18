# Examples

The repository's [examples README](https://github.com/smuniharish/contextsage/blob/master/examples/README.md) lists setup,
dependencies and commands. Offline examples use scripted models, run without
provider credentials, and are checked against recorded output.

## Core and framework integration

| Example | Demonstrates |
| --- | --- |
| [Quickstart](https://github.com/smuniharish/contextsage/blob/master/examples/quickstart.py) | Async framework-neutral engine, facts, compaction and events |
| [Custom framework](https://github.com/smuniharish/contextsage/blob/master/examples/custom_framework.py) | `FrameworkAdapter` implementation and lineage between generations |
| [LangChain agent](https://github.com/smuniharish/contextsage/blob/master/examples/langchain_agent.py) | Optional LangChain integration |
| [Downstream customization](https://github.com/smuniharish/contextsage/blob/master/examples/downstream_customization.py) | parsefabric and agxai component customization |

## Summarization behavior

| Example | Demonstrates |
| --- | --- |
| [Large tool output](https://github.com/smuniharish/contextsage/blob/master/examples/large_tool_output.py) | Compaction of mixed structured content |
| [Preservation](https://github.com/smuniharish/contextsage/blob/master/examples/preservation.py) | Required facts and conflicts |
| [Policies](https://github.com/smuniharish/contextsage/blob/master/examples/policies.py) | Built-in and custom preservation policies |
| [Recovery](https://github.com/smuniharish/contextsage/blob/master/examples/recovery.py) | Safe trimming after model failure |
| [Custom parsing](https://github.com/smuniharish/contextsage/blob/master/examples/custom_parsing.py) | A custom parsefabric parser route |
| [Provenance](https://github.com/smuniharish/contextsage/blob/master/examples/provenance.py) | Lineage queries and deletion |
| [Observability](https://github.com/smuniharish/contextsage/blob/master/examples/observability.py) | Custom events and OpenTelemetry metrics |
| [Prometheus](https://github.com/smuniharish/contextsage/blob/master/examples/observability_prometheus.py) | A custom Prometheus event sink |

## Service-backed and live examples

[PostgreSQL provenance](https://github.com/smuniharish/contextsage/blob/master/examples/postgres_store.py) demonstrates an agxai
store implementation. [OpenTelemetry export](https://github.com/smuniharish/contextsage/blob/master/examples/otel_export.py)
sends traces and metrics through a collector to Jaeger.

The live examples use an OpenAI-compatible provider and require
`CONTEXTSAGE_LLM_API_KEY`: [LangChain agent](https://github.com/smuniharish/contextsage/blob/master/examples/live_agent.py),
[Deep Agent](https://github.com/smuniharish/contextsage/blob/master/examples/deep_agent.py), and
[LangGraph swarm](https://github.com/smuniharish/contextsage/blob/master/examples/swarm.py).
