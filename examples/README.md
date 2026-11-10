# ContextSage examples

Runnable examples of ContextSage's async, framework-neutral summarization
engine and its integrations. Offline examples use scripted models, run without
network access or API keys, and have exact output checked by
[`verify_examples.py`](verify_examples.py).

## Setup

From the repository root:

```powershell
uv sync --all-extras --all-groups
```

The `examples` dependency group includes the optional agent integrations,
PostgreSQL driver, Prometheus client, and SQL parser used by these scripts.

## Offline examples

| Example | What it shows |
| --- | --- |
| [`quickstart.py`](quickstart.py) | The framework-neutral `ContextSummarizer` on plain message objects. |
| [`langchain_agent.py`](langchain_agent.py) | The LangChain middleware inside a `create_agent` loop. |
| [`custom_framework.py`](custom_framework.py) | An OpenAI-style message adapter and lineage across summary generations. |
| [`downstream_customization.py`](downstream_customization.py) | Custom `Tokenizer`, `ExecutionBackend`, parsefabric sink, agxai store, capture policy, and observability provider. |
| [`large_tool_output.py`](large_tool_output.py) | Compacting a large mixed tool result while retaining distinct errors and identifiers. |
| [`preservation.py`](preservation.py) | Restating corrections, instructions, identifiers, and conflicting evidence. |
| [`policies.py`](policies.py) | Built-in and custom preservation policies. |
| [`recovery.py`](recovery.py) | Trimming safely when the summary model fails. |
| [`custom_parsing.py`](custom_parsing.py) | Routing SQL content to a custom parsefabric parser. |
| [`provenance.py`](provenance.py) | Tracing summaries back to the original messages. |
| [`observability.py`](observability.py) | Custom events, structured logging, and in-memory OpenTelemetry metrics. |
| [`observability_prometheus.py`](observability_prometheus.py) | A custom event sink exporting Prometheus metrics; [`observability_prometheus.yml`](observability_prometheus.yml) is a scrape configuration. |

Run one, for example:

```powershell
uv run --group examples --extra langchain --extra otel python examples\quickstart.py
```

Verify every offline example:

```powershell
uv run --group examples --extra langchain --extra otel python examples\verify_examples.py
```

After an intentional output change, re-record with `--update` and review
the diff under [`expected/`](expected/).

## Service-backed examples

### PostgreSQL provenance store

Start PostgreSQL 18 with Podman:

```powershell
podman run --rm -d --name contextsage-postgres -p 5432:5432 `
  -e POSTGRES_USER=contextsage -e POSTGRES_PASSWORD=contextsage `
  -e POSTGRES_DB=contextsage docker.io/library/postgres:18
$env:CONTEXTSAGE_POSTGRES_DSN = "postgresql://contextsage:contextsage@localhost:5432/contextsage"
uv run --group examples --extra langchain python examples\postgres_store.py
```

[`postgres_store.py`](postgres_store.py) implements the agxai
`ProvenanceStore` ABC, writes lineage to a JSONB table, reads the lineage
back through a new runtime, and deletes the thread's records. On Windows, psycopg uses a selector event loop and the store serializes
operations over one async connection. Other platforms use its async pool.

### OpenTelemetry and Jaeger

Create a network, then start Jaeger and the collector:

```powershell
podman network create contextsage-observability
podman run --rm -d --name contextsage-jaeger --network contextsage-observability `
  -p 16686:16686 -p 4317:4317 docker.io/jaegertracing/all-in-one:latest
podman run --rm -d --name contextsage-otel --network contextsage-observability `
  -p 4318:4318 `
  -v "${PWD}\examples\otel_collector.yml:/etc/otelcol-contrib/config.yaml:ro" `
  docker.io/otel/opentelemetry-collector-contrib:latest `
  --config=/etc/otelcol-contrib/config.yaml
uv run --group examples --extra otel python examples\otel_export.py
```

[`otel_export.py`](otel_export.py) sends ContextSage traces and metrics to the
collector using OTLP HTTP. The collector forwards traces to Jaeger over OTLP
gRPC and reports both signals to its debug exporter. View traces at
http://localhost:16686.

### Prometheus

[`observability_prometheus.py`](observability_prometheus.py) serves metrics on
http://localhost:9109/metrics for the duration set by
`OBSERVABILITY_DEMO_SECONDS` (default 60). Run it and Prometheus on the same
Podman network so the scrape target resolves:

```powershell
podman network create contextsage-metrics
podman run --rm -d --name contextsage-prometheus-exporter --network contextsage-metrics `
  -e OBSERVABILITY_DEMO_SECONDS=180 -v "${PWD}:/workspace" `
  docker.io/library/python:3.13-slim sh -c `
  'pip install -q -e "/workspace[langchain]" prometheus-client && PYTHONPATH=/workspace/examples python /workspace/examples/observability_prometheus.py'
podman run --rm -d --name contextsage-prometheus --network contextsage-metrics `
  -p 9090:9090 `
  -v "${PWD}\examples\observability_prometheus.yml:/etc/prometheus/prometheus.yml:ro" `
  docker.io/prom/prometheus:latest --config.file=/etc/prometheus/prometheus.yml
```

Query `contextsage_summarizations_total` in Prometheus at http://localhost:9090.
[`observability_prometheus.yml`](observability_prometheus.yml) contains the
scrape configuration.

## Live LLM examples

These call a real model through an OpenAI-compatible chat-completions
endpoint:

| Example | What it shows |
| --- | --- |
| [`live_agent.py`](live_agent.py) | A LangChain agent whose diagnostic tool returns a large report. |
| [`deep_agent.py`](deep_agent.py) | ContextSage as the memory compactor for a deep agent. |
| [`swarm.py`](swarm.py) | ContextSage on one agent of a LangGraph swarm. |

Copy the repository's `.env.example` to `.env`, or set:

| Variable | Meaning |
| --- | --- |
| `CONTEXTSAGE_LLM_API_KEY` | API key; required. |
| `CONTEXTSAGE_LLM_BASE_URL` | Base URL ending in `/v1`; defaults to OpenAI. |
| `CONTEXTSAGE_LLM_MODEL` | Model name; defaults to `gpt-5-mini`. |

For example:

```powershell
uv run --group examples --extra langchain python examples\live_agent.py
```
