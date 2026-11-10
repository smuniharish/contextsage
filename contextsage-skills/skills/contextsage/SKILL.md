---
name: contextsage
description: >-
  Use this skill when integrating, configuring, testing, or debugging the
  ContextSage Python package in an AI agent: long histories, large tool
  results, lost facts, summary-model failures, async framework adapters,
  LangChain integration, summary events, or provenance. Use contextsage-extend
  when implementing a custom framework adapter, parser, event sink, token
  counter, preservation policy, or downstream agxai/parsefabric component.
  Do not use it to build retrieval or long-term memory, or to summarize
  documents outside an agent conversation.
license: Apache-2.0
compatibility: >-
  Python 3.12 or newer. Install contextsage from PyPI; install
  contextsage[langchain] for the optional LangChain and LangGraph integration.
metadata:
  version: "1.0.1"
  documentation: "https://contextsage.readthedocs.io/"
---

# ContextSage

ContextSage is an asynchronous, framework-neutral engine for summarizing
agent message histories while preserving facts, tool relationships and
lineage. The core uses `contextsage.Message` and a parsefabric
`LanguageModel`; LangChain support is an optional integration.

Read the [quickstart](https://contextsage.readthedocs.io/en/latest/getting-started/quickstart/)
and [API reference](https://contextsage.readthedocs.io/en/latest/reference/)
for signatures. The source of truth is
[`src/contextsage/`](https://github.com/smuniharish/contextsage/tree/master/src/contextsage),
the runnable [examples](https://github.com/smuniharish/contextsage/tree/master/examples),
and [tests](https://github.com/smuniharish/contextsage/tree/master/tests).

## Activate when

Use this skill when an agent needs a smaller live conversation history
without losing important context:

- Tool output contains large logs, JSON, tables, code or stack traces.
- Summaries lose identifiers, user corrections, instructions or conflicting
  values.
- A framework needs an async adapter or LangChain summarization integration.
- The application needs summary events, recovery behavior or lineage queries.

Do not treat ContextSage as retrieval, durable memory, a general document
summarizer or a replacement for the agent framework.

## Workflow

1. Check the installed ContextSage version, Python version and framework. The
   core package requires Python 3.12 or newer and does not install LangChain.
2. Select the integration boundary:
   - Use `ContextSummarizer` directly for a framework-neutral loop.
   - Install `contextsage[langchain]` for
     `contextsage.integrations.langchain`.
   - Use `contextsage-extend` to implement a custom adapter or dependency
     component.
3. Configure the summary model, trigger, retained window and actual context
   budget. Implement `parsefabric.LanguageModel` or use the optional
   `LangChainSummaryModel`.
4. Preserve lineage in framework messages or checkpoint metadata. Pass the
   same `thread_id` to `summarize` and `lineage`.
5. Add a scripted-model test for the representative history and failure
   cases. Run the focused tests and relevant package checks.

## Core usage

Convert native messages with `FrameworkAdapter`, then use the returned
history only when the engine produces a result:

```python
async def summarize_turn(engine, messages, thread_id):
    result = await engine.summarize(messages, thread_id=thread_id)
    if result is None:
        return messages
    return list(result.messages)
```

`summarize` returns `None` when no trigger fires. When it rewrites a history,
the `SummarizationResult` contains the complete replacement messages and a
content-free `SummarizationEvent`.

## Configuration guide

| Need | Use |
| --- | --- |
| Trigger | `("tokens", n)`, `("messages", n)`, a conjunction mapping, or a list of alternatives |
| Keep recent context | `keep=("messages", n)`, token count, or context-window fraction |
| Preserve domain identifiers | Extend `DEFAULT_IDENTIFIER_PATTERNS` with compiled regexes |
| Change content parsing | `ParsingOptions` and parsefabric extension points |
| Change preservation behavior | A built-in policy or `PreservationPolicy` ABC |
| Count model tokens | `TokenCounter` ABC or parsefabric `Tokenizer` through `TokenizerTokenCounter` |
| Export events | `EventSink`, `CompositeEventSink`, or `OpenTelemetryEventSink` |
| Persist lineage | Supply an agxai `ProvenanceStore` through `create_agxai_runtime` |

Use `ContextSummarizer.prepare()` during startup when parsing resources must
be validated before traffic. Keep cancellation propagation intact. List
framework control-flow exception types in `propagate_errors`; ordinary model
failures use the bounded trimming fallback.

## LangChain integration

Install `contextsage[langchain]` and import
`IntelligentSummarizationMiddleware` from
`contextsage.integrations.langchain`. Use it in LangChain agent middleware;
do not instantiate the integration through a core-package import. The
integration adapts native messages, summary-model calls, token counting and
framework control-flow errors.

For Deep Agents or LangGraph Swarm, inspect the installed versions and follow
their documented middleware APIs. Do not assume framework-specific setup
that is not shown in the current examples:
[LangChain](https://github.com/smuniharish/contextsage/blob/master/examples/langchain_agent.py),
[Deep Agent](https://github.com/smuniharish/contextsage/blob/master/examples/deep_agent.py),
[swarm](https://github.com/smuniharish/contextsage/blob/master/examples/swarm.py).

## Rules

- Keep application integration asynchronous and framework-specific code at
  the adapter boundary.
- Do not infer public arguments from private modules; use the API reference.
- Keep `validation_enabled=True` unless a separately tested validation layer
  replaces it.
- Do not log message content or use conversation IDs as metric labels.
- Store lineage metadata with checkpointed messages so later summaries can
  continue the ancestry chain.
- For a custom component, follow the `contextsage-extend` skill and subclass
  the documented ABC.

## Verify

- Test a history below and above the configured trigger.
- Assert important IDs and corrections remain in the returned history.
- Test summary-model failure and framework control-flow exceptions.
- Verify `SummarizationEvent` statuses and provenance queries.
- Run the repository's targeted tests, examples and type checks for the
  changed surface.

For service-backed examples, dependency inventory and operational guidance,
see the [documentation](https://contextsage.readthedocs.io/).
