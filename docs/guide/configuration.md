# Configuration

`ContextSummarizer` takes a `parsefabric.LanguageModel` and optional policies,
budgets, parsers, sinks and an agxai runtime:

```python
async def summarize_history(model, messages):
    async with ContextSummarizer(
        model,
        trigger=("tokens", 100_000),
        keep=("messages", 20),
        maximum_context_tokens=128_000,
    ) as summarizer:
        result = await summarizer.summarize(messages, thread_id="thread-42")
```

All model and engine operations are asynchronous. Use the context manager to
close resources owned by the summarizer.

## Triggers and retained context

`trigger` accepts one threshold, a conjunction, or a disjunction:

```python
("tokens", 8_000)  # one threshold
{"tokens": 8_000, "messages": 12}  # every condition must hold
[("tokens", 8_000), ("messages", 40)]  # either condition may hold
```

Threshold units are `tokens`, `messages`, and `fraction`. A fraction is of
`maximum_context_tokens`. When `trigger=None`, the engine runs when the
history would exceed the available input budget.

`keep` accepts `("messages", n)`, `("tokens", n)`, or `("fraction", f)` and
controls the recent history kept outside the summary. Leading system messages
are retained.

## Context budget

| Argument | Default | Purpose |
| --- | ---: | --- |
| `maximum_context_tokens` | 128,000 | Model context window |
| `reserved_output_tokens` | 4,000 | Space reserved for the agent response |
| `safety_margin` | 0.10 | Fraction of the context window held as a buffer |
| `summarization_overhead_tokens` | 2,000 | Space for prompts, system messages and tool schemas |
| `trim_tokens_to_summarize` | 4,000 | Maximum transcript size sent to the summary model; `None` sends all |

Use the model's actual context window and reserve adequate space for the
agent's system prompt and tools.

## Token counting and preservation

Implement `TokenCounter` when the model uses a tokenizer with different
counting rules. The default `TokenizerTokenCounter` accepts a parsefabric
`Tokenizer`. Choose a built-in `PreservationPolicy` or implement the
`PreservationPolicy` ABC. Structural signals such as user corrections,
identifiers associated with errors, and both sides of contradictions remain
protected under every policy.

`identifier_patterns` replaces the default compiled regular expressions. To
extend them, pass `[*DEFAULT_IDENTIFIER_PATTERNS, your_pattern]`.
`validation_enabled` controls fact validation and restatement.

## Parsing and extension components

`parsing=ParsingOptions(...)` forwards parsefabric's supported customizations:
patterns, routes, fenced-code parsers, code detector, JSON codec, parser
registry, lifecycle sink, execution backend, and parse concurrency. See
[content parsing](content-parsing.md).

`sink` receives ContextSage's `SummarizationEvent`; its default is
`LoggingEventSink`. `runtime` is an agxai `XAIRuntime`, configurable with
`create_agxai_runtime(...)`. See [observability](observability.md) and
[provenance](provenance.md).

## Summary model and errors

The summary model implements parsefabric's `LanguageModel` ABC. The prompt
must include `{messages}`. Exceptions raised by the summary model cause a
safe trim fallback unless their type appears in `propagate_errors`.
Cancellation is always propagated.

For framework integration arguments, see [integrations](integrations.md).
