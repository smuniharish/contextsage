# Configuration

`IntelligentSummarizationMiddleware` takes the summary model as its only
positional argument. Every other argument is keyword-only and has a default
suited to production. Invalid values raise `contextsage.ConfigurationError`
when the middleware is created, never in the middle of an agent run.

```python
from contextsage import IntelligentSummarizationMiddleware

middleware = IntelligentSummarizationMiddleware(model="openai:gpt-5-mini")
```

## Arguments at a glance

| Argument | Default | Purpose |
| --- | --- | --- |
| `model` | required | Chat model, or `init_chat_model` identifier, that writes summaries |
| `trigger` | `None` | When to summarize; `None` means "when the history exceeds the budget" |
| `keep` | `("messages", 20)` | Recent history that the summary does not replace |
| `policy` | `"balanced"` | How readily content is compacted; see [Preservation policies](policies.md) |
| `maximum_context_tokens` | model profile, else 128,000 | The model's context window |
| `reserved_output_tokens` | `4_000` | Tokens kept free for the model's response |
| `safety_margin` | `0.10` | Fraction of the window held back as a buffer |
| `summarization_overhead_tokens` | `2_000` | Tokens kept free for the system prompt, tool schemas and the summary prompt |
| `token_counter` | LangChain's counter for the model | Counts the tokens of a list of messages |
| `routes` | `()` | Extra parsefabric routes; see [Content parsing](content-parsing.md) |
| `fence_routes` | `None` | parsefabric parsers for fenced blocks, by language tag |
| `code_languages` | parsefabric's defaults | tree-sitter grammars used to detect unfenced code |
| `identifier_patterns` | `DEFAULT_IDENTIFIER_PATTERNS` | Regular expressions for identifiers that must survive |
| `validation_enabled` | `True` | Check the rewritten history and restate missing facts |
| `observability_hook` | `None` | Called with every `SummarizationEvent`; see [Observability](observability.md) |
| `provenance_store` | in-memory store | langgraph-xai store for provenance links; see [Provenance and lineage](provenance.md) |
| `summary_prompt` | LangChain's prompt | Prompt for the summary model, with a `{messages}` placeholder |
| `trim_tokens_to_summarize` | `4_000` | Token budget for the messages sent to the summary model, or `None` for all |

## When to summarize

`trigger` accepts every form LangChain's `SummarizationMiddleware` accepts,
plus `None`:

| `trigger=` | Summarizes when |
| --- | --- |
| `None` | The history no longer fits the input budget (below) |
| `("tokens", 100_000)` | The history has at least 100,000 tokens |
| `("messages", 50)` | The history has at least 50 messages |
| `("fraction", 0.8)` | The history uses at least 80% of `maximum_context_tokens` |
| `{"tokens": 4_000, "messages": 10}` | Every condition of the clause holds |
| `[("tokens", 100_000), {"tokens": 4_000, "messages": 10}]` | Any item of the list holds |

The `trigger_reason` of each event says which condition fired:

```python
from itertools import cycle

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.runtime import Runtime

from contextsage import IntelligentSummarizationMiddleware, SummarizationEvent

events: list[SummarizationEvent] = []
middleware = IntelligentSummarizationMiddleware(
    model=GenericFakeChatModel(messages=cycle([AIMessage("Summary.")])),
    trigger=[("tokens", 100_000), {"tokens": 50, "messages": 6}],
    keep=("messages", 2),
    observability_hook=events.append,
)
history = [HumanMessage(f"Question {index} about the order.") for index in range(6)]
middleware.before_model({"messages": history}, Runtime())
print(events[0].trigger_reason)
```

Output:

```text
66 tokens >= 50 and 6 messages >= 6
```

## How much to keep

`keep` sets how much recent history the summary does not replace:
`("messages", 20)` keeps the last 20 messages, `("tokens", 3_000)` the last
3,000 tokens and `("fraction", 0.3)` the last 30% of `maximum_context_tokens`,
which also works for models without a LangChain profile. The summary never
separates a tool call from its result.

`keep` does not limit compaction: large tool results in the kept messages are
compacted too, because that is usually where the tokens are.

## The token budget

The budget accounts for the whole context window explicitly:

```text
available tokens = maximum_context_tokens
                 - reserved_output_tokens
                 - maximum_context_tokens × safety_margin
                 - summarization_overhead_tokens
```

`maximum_context_tokens` defaults to the `max_input_tokens` of the model's
LangChain profile, which LangChain provides for most models, and to 128,000
otherwise. With `trigger=None`, summarization runs when the history exceeds the
available tokens. A budget that leaves no room for input raises
`ConfigurationError`.

## Token counting

By default, tokens are counted the way LangChain's `SummarizationMiddleware`
counts them for the model: a fast approximation that is calibrated by the
token usage your provider reports. To count exactly, pass any callable that
takes a list of messages and returns a token count, such as a chat model's
`get_num_tokens_from_messages`. Exact counting is slower, and the counter runs
before every model call.

## Identifiers

Identifiers are values that must survive every summary verbatim. The defaults
in `contextsage.DEFAULT_IDENTIFIER_PATTERNS` match UUIDs, keys such as
`INC-9931`, assignments such as `request_id=req-7` and phrases such as
`customer 456`. Add your own formats to the defaults:

```python
import re

from contextsage import DEFAULT_IDENTIFIER_PATTERNS, IntelligentSummarizationMiddleware

middleware = IntelligentSummarizationMiddleware(
    model="openai:gpt-5-mini",
    identifier_patterns=[
        *DEFAULT_IDENTIFIER_PATTERNS,
        re.compile(r"\bWO-\d{6}\b"),
        re.compile(r"\bSKU-[A-Z0-9]{8}\b"),
    ],
)
```

Patterns run on untrusted text, so keep them linear-time: avoid nested and
overlapping quantifiers such as `(a+)+`.

## Summary prompt

`summary_prompt` and `trim_tokens_to_summarize` are passed to LangChain's
`SummarizationMiddleware` unchanged. A custom prompt must contain a
`{messages}` placeholder. ContextSage does not depend on the summary's wording:
validation checks the facts whatever the prompt asks for.

## Errors

| Error | Raised when |
| --- | --- |
| `ConfigurationError` | An argument is invalid, the model identifier cannot be initialized, or the code-detection grammars cannot be loaded |
| `ContextSageError` | The base class of every ContextSage error |

`ConfigurationError` is also a `ValueError`. Once the middleware is created,
summarization never fails an agent run: model errors are recovered from, and
provenance and observability failures are logged. Interrupts and other
LangGraph control-flow signals pass through unchanged.
