# ContextSage

[![CI](https://github.com/smuniharish/contextsage/actions/workflows/ci.yml/badge.svg)](https://github.com/smuniharish/contextsage/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

**ContextSage** is an intelligent, production-grade replacement for
LangGraph's built-in `SummarizationMiddleware`. It adds an information-aware
planning layer on top of LangGraph/LangChain's existing summarization
mechanism, so that when an agent's context grows too large, ContextSage
decides *what* should be preserved, compressed, or left untouched — instead
of blindly summarizing "the oldest messages first".

```python
from langchain.agents import create_agent
from contextsage import IntelligentSummarizationMiddleware

middleware = IntelligentSummarizationMiddleware(
    model=model,
    trigger=("tokens", 100_000),
    keep=("messages", 20),
)

agent = create_agent(
    model=model,
    tools=tools,
    middleware=[middleware],
)
```

That's it. Everything else — context decomposition, importance scoring,
preservation requirements, provenance tracking, validation, and recovery —
happens automatically inside the middleware.

## Why ContextSage?

Modern agents accumulate **heterogeneous** context: natural language, JSON,
logs, stack traces, tool metadata, tables, and code, often mixed together in
a single large tool result. LangGraph's `SummarizationMiddleware` is a solid,
general-purpose building block, but it does not:

- distinguish between critical and disposable information,
- protect user corrections and active constraints from being lost,
- deterministically compress structured/log content instead of paying for
  an LLM call on data an LLM doesn't need to read,
- validate that a summary didn't silently drop something important,
- recover gracefully if summarization fails or a summary is invalid.

ContextSage adds exactly this intelligence layer, while **reusing** — not
reimplementing or forking — LangGraph's own semantic summarization for the
parts only an LLM can do well.

## Principle

> Information preservation > raw token reduction.

A smaller summary that loses a customer ID, a user correction, or a root
cause is a failure, even if it saves tokens. ContextSage's planner is
budget-aware *and* information-aware.

## Installation

```bash
pip install contextsage
```

`langgraph-xai` is installed automatically as a direct dependency and used
internally for provenance/evidence tracking — no separate setup required.
Authoritative OpenAI-compatible token counting via `tiktoken`, and real
code-structure detection via `tree-sitter`, are also core dependencies —
no optional extras to install for ContextSage's default behavior.

## How it works

```
Complete context
      |
      v
Heterogeneous context decomposition -> Context units
      |
      v
Structural signals -> Importance -> Relationships / Provenance
      |
      v
Preservation requirements -> Summarization plan
      |
      v
Selective deterministic transformation
      |
      v
LangGraph semantic summarization (reused, not forked)
      |
      v
Validation -> Recovery (if needed) -> Reconstruction
```

See [docs/architecture.md](docs/architecture.md) for the full design and
[docs/](docs/) for component-level documentation.

## Examples

Runnable examples live in [examples/](examples/) and call a real,
network-backed chat model (via [examples/_llm.py](examples/_llm.py)) so
their output reflects genuine model behavior rather than a scripted fake.
Install the `examples` extra, then copy `.env.example` to `.env` and set
`EXPLABS_API_KEY`:

```bash
pip install -e ".[examples]"
cp .env.example .env  # then fill in EXPLABS_API_KEY
python examples/basic.py
```

| Example | Demonstrates |
|---|---|
| [basic](examples/basic.py) | The minimal end-to-end quickstart. |
| [large_tool_output](examples/large_tool_output.py) | A single large mixed JSON+log `ToolMessage` with a preserved transaction ID and root cause. |
| [mixed_mcp_output](examples/mixed_mcp_output.py) | Heterogeneous MCP-style tool output (text + JSON + logs) in one message. |
| [logs](examples/logs.py) | Log-heavy content with trace ID and root-cause preservation. |
| [rag](examples/rag.py) | Contradiction-preserving behavior across conflicting retrieval sources. |
| [structured_data](examples/structured_data.py) | JSON/structured-data preservation across multiple tool results. |
| [recovery](examples/recovery.py) | Graceful fallback when the summarization LLM call itself fails (uses an intentionally-failing model, not the real one). |
| [policy](examples/policy.py) | How `policy="maximum_preservation" \| "balanced" \| "maximum_compression"` changes preservation outcomes (no model call). |
| [all_parameters](examples/all_parameters.py) | Every `IntelligentSummarizationMiddleware` constructor parameter set to an explicit non-default value, each one's effect independently verified (budget math, `parsers`, `token_counter`, `observability_hook`, provenance/lineage, `summary_prompt`/`trim_tokens_to_summarize`, ...). |
| [sql_parser](examples/sql_parser.py) | A custom `SQLContentParser` (`parsers=[...]`) built on the production-grade `sqlglot` package — demonstrates the `parsers` extension point classifying, isolating, and preserving SQL content, plus overriding its own `keyword_pattern`/`dialect` rules, without any SQL dependency forced into core. |
| [agent_create_agent](examples/agent_create_agent.py) | `langchain.agents.create_agent` running a real compiled LangGraph agent, with the middleware triggering mid-run inside the agent's own loop. |
| [deep_agent](examples/deep_agent.py) | `deepagents.create_deep_agent` — the middleware plugs into a deep agent's own (larger) graph the same way. |
| [swarm](examples/swarm.py) | `langgraph_swarm.create_swarm` — a two-agent swarm with a real handoff tool; the middleware is attached to only one specialist agent and runs across checkpointed multi-turn state. Requires the `deepagents`/`langgraph-swarm` extras (installed with `examples`). |

## What ContextSage is not

- Not an agent framework, memory framework, or a replacement for LangGraph/LangChain.
- Not a general-purpose parser/document-processing framework.
- Not a new plugin platform — there is no public plugin registry.

ContextSage stays narrowly focused on one job: intelligent context
summarization for LangGraph/LangChain agents.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and pull
request guidelines. This project follows the
[Code of Conduct](CODE_OF_CONDUCT.md). For security issues, see
[SECURITY.md](SECURITY.md) instead of opening a public issue.

## License

Apache License 2.0. See [LICENSE](LICENSE).
