# ContextSage

[![PyPI](https://img.shields.io/pypi/v/contextsage)](https://pypi.org/project/contextsage/)
[![Python](https://img.shields.io/pypi/pyversions/contextsage)](https://pypi.org/project/contextsage/)
[![CI](https://github.com/smuniharish/contextsage/actions/workflows/ci.yml/badge.svg)](https://github.com/smuniharish/contextsage/actions/workflows/ci.yml)
[![Documentation](https://img.shields.io/readthedocs/contextsage)](https://contextsage.readthedocs.io/)
[![License](https://img.shields.io/pypi/l/contextsage)](https://github.com/smuniharish/contextsage/blob/master/LICENSE)

**Information-aware context summarization for AI agents.** ContextSage
compresses long conversation histories while preserving important facts,
tool relationships and provenance. The asynchronous core uses a framework-
neutral message model; integrations connect it to frameworks such as
LangChain, Agno and CrewAI.

## Install

```bash
pip install contextsage
```

Install optional integrations only when you use them:

```bash
pip install "contextsage[langchain]"  # LangChain and LangGraph
pip install "contextsage[otel]"       # OpenTelemetry SDK and OTLP exporter
pip install "contextsage[all]"        # both optional integrations
```

The core requires Python 3.12 or newer and does not install an agent framework.

## Framework-neutral quickstart

Implement `parsefabric.LanguageModel` with your summary provider, convert your
framework's history to `contextsage.Message`, then call the async engine before
the next model turn:

```python
async def summarize_history(summary_model, messages):
    async with ContextSummarizer(summary_model, trigger=("tokens", 100_000)) as engine:
        result = await engine.summarize(messages, thread_id="conversation-42")
        if result is not None:
            messages = list(result.messages)
```

The engine parses text and structured content, compacts repetitive material,
preserves facts such as identifiers and corrections, validates the result,
and records lineage. If the history does not meet the trigger, `summarize`
returns `None`. See the runnable [quickstart](examples/quickstart.py) and the
[core concepts](docs/guide/how-it-works.md).

## Integrations

The optional LangChain integration wraps the same core engine:

```python
from contextsage.integrations.langchain import IntelligentSummarizationMiddleware

middleware = IntelligentSummarizationMiddleware(
    "openai:gpt-5-mini",
    trigger=("tokens", 100_000),
    keep=("messages", 20),
)
```

Or implement `FrameworkAdapter` for your framework's message type. The
adapter maps between native messages and the neutral `Message` model; no
framework dependency is needed by the core. See the [LangChain integration](docs/guide/integrations.md)
and [custom framework example](examples/custom_framework.py).

## Downstream customization

ContextSage exposes the extension points of its dependencies rather than
restricting them to built-in choices:

| Package | Customizable components |
| --- | --- |
| [parsefabric](https://pypi.org/project/parsefabric/) | `LanguageModel`, tokenizers, line patterns, parsers and registries, fenced-code routes, code detection, JSON codec, lifecycle sink, and execution backend. |
| [agxai](https://pypi.org/project/agxai/) | `ProvenanceStore`, observability, attribution, explanation and policy providers, capture policy, runtime configuration, registry, plugins, and custom state capture. |
| OpenTelemetry | Use the built-in event sink and SDK/exporters, or supply an `EventSink` for your telemetry platform. |
| LangChain (optional) | Supply a chat model, token counter, and `LangChainAdapter` to the integration. |

Use `ParsingOptions` to configure parsefabric and
`create_agxai_runtime(...)` to configure agxai. The
[downstream customization example](examples/downstream_customization.py)
demonstrates custom components from both packages.

## Examples and documentation

The [examples](examples/README.md) include framework adapters, LangChain,
PostgreSQL provenance, OpenTelemetry, Prometheus, custom parsing, policies,
and recovery. Scripted examples run without API keys and their output is
verified in CI. The
[documentation site](https://contextsage.readthedocs.io/) includes
installation, configuration, integration guides, operations guidance and the
[API reference](https://contextsage.readthedocs.io/en/latest/reference/).

ContextSage also publishes an [Agent Skill](contextsage-skills/README.md) for
coding agents that need to integrate or extend the package.

## Development

```bash
uv sync --locked --all-extras --all-groups
uv run pytest
uv run ruff check .
uv run pyrefly check
```

See [contributing](CONTRIBUTING.md) and [testing](docs/development/testing.md).
ContextSage is licensed under the [Apache License 2.0](LICENSE).
