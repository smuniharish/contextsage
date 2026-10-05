# ContextSage examples

Runnable examples of `IntelligentSummarizationMiddleware`. The offline examples
use scripted chat models, so they run without network access or API keys and
always print the same output. `verify_examples.py` checks them against the
recorded output in [`expected/`](expected/).

## Setup

From the repository root:

```bash
uv sync
```

The default `dev` dependency group includes everything the examples need:
`langchain-openai`, `deepagents`, `langgraph-swarm`, `sqlglot`,
`prometheus-client` and `python-dotenv`.

## Offline examples

| Example | What it shows |
| --- | --- |
| [`quickstart.py`](quickstart.py) | ContextSage in a `create_agent` agent: compaction, summary and validation in one turn. |
| [`large_tool_output.py`](large_tool_output.py) | Compacting a large mixed tool result: repeated log lines and JSON records collapse; warnings, errors and identifiers stay. |
| [`preservation.py`](preservation.py) | A vague summary loses a correction, an instruction, identifiers and conflicting evidence; ContextSage restates them. |
| [`policies.py`](policies.py) | The same JSON payload under the three preservation policies. |
| [`recovery.py`](recovery.py) | The summary model fails; the history is trimmed without orphaning a tool result, and the lost facts are restated. |
| [`custom_parsing.py`](custom_parsing.py) | A parsefabric parser, built on `sqlglot`, that teaches ContextSage to recognize SQL. |
| [`provenance.py`](provenance.py) | Tracing a summary of a summary back to the original messages. |
| [`observability.py`](observability.py) | The structured event behind every summarization, through logging and a hook. |
| [`observability_prometheus.py`](observability_prometheus.py) | Exporting events as Prometheus metrics; [`observability_prometheus.yml`](observability_prometheus.yml) is a scrape configuration. |

Run one with, for example:

```bash
uv run python examples/quickstart.py
```

Verify all of them with:

```bash
uv run python examples/verify_examples.py
```

After an intentional change in behavior, re-record the output with
`--update` and review the diff in `expected/`.

## Live examples

These call a real model through any OpenAI-compatible chat completions
endpoint:

| Example | What it shows |
| --- | --- |
| [`live_agent.py`](live_agent.py) | A `create_agent` agent whose tool returns a large diagnostics report. |
| [`deep_agent.py`](deep_agent.py) | Replacing the built-in summarization of a `deepagents` deep agent. |
| [`swarm.py`](swarm.py) | ContextSage on one agent of a `langgraph-swarm` multi-agent swarm. |

Configure the endpoint with environment variables, or copy
[`.env.example`](../.env.example) to `.env` (which git ignores):

| Variable | Meaning |
| --- | --- |
| `CONTEXTSAGE_LLM_API_KEY` | API key. Required. |
| `CONTEXTSAGE_LLM_BASE_URL` | Base URL ending in `/v1`. Defaults to OpenAI. |
| `CONTEXTSAGE_LLM_MODEL` | Model name. Defaults to `gpt-5-mini`. |

```bash
uv run python examples/live_agent.py
```
