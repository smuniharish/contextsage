# ContextSage

**Information-aware context summarization for AI agents.** ContextSage
compresses long conversation histories while preserving facts, tool-call
relationships and traceable provenance.

The asynchronous core works with a framework-neutral message model. Adapt
messages from any agent framework with `FrameworkAdapter`, or use the optional
LangChain integration. The core itself does not install an agent framework.

## What it does

- Parses messages into prose, JSON, logs, tables, code and stack traces.
- Compacts repetitive structured content before it reaches the summary model.
- Preserves user corrections, instructions, identifiers and conflicting facts.
- Validates the rewritten history and restores any missing required facts.
- Trims safely if the summary model fails.
- Records lineage with agxai and emits content-free summary events.

## Quick look

```python
async def summarize_history(summary_model, messages):
    async with ContextSummarizer(
        summary_model,
        trigger=("tokens", 100_000),
        keep=("messages", 20),
    ) as summarizer:
        result = await summarizer.summarize(messages, thread_id="conversation-42")
        if result is not None:
            messages = list(result.messages)
```

`summary_model` implements `parsefabric.LanguageModel`; `messages` is a
sequence of `contextsage.Message`. The engine returns `None` when the trigger
does not fire. See the [quickstart](getting-started/quickstart.md) for a
complete runnable example.

## Choose an integration

| Your agent | Use |
| --- | --- |
| Any framework or a hand-written loop | `ContextSummarizer` and a `FrameworkAdapter` |
| LangChain or LangGraph | `contextsage[langchain]` and `contextsage.integrations.langchain` |
| Another framework | Implement an adapter for its message type; no core framework dependency is needed |

## Downstream extension points

ContextSage exposes the customization offered by its dependencies:

- **parsefabric:** model and tokenizer abstractions, parsing patterns and
  parsers, registries, fenced-code routes, code detection, JSON codecs,
  lifecycle sinks and execution backends.
- **agxai:** provenance stores, observability, attribution, explanation and
  policy providers, capture policies, runtime settings, registries, plugins,
  and custom state capture.
- **ContextSage:** ABCs for framework adapters, token counters, preservation
  policies and event sinks, plus the OpenTelemetry event sink.

See [downstream customization](guide/integrations.md#downstream-customization)
for the complete component inventory and setup.

## Get started

- [Install the core or an optional integration](getting-started/installation.md).
- [Run the quickstart](getting-started/quickstart.md).
- [Configure triggers, budgets and policies](guide/configuration.md).
- [Browse examples](examples.md).
- [Read the API reference](reference/index.md).
