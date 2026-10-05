---
name: contextsage
description: Integrate, configure, debug, or test the contextsage Python middleware, an information-aware replacement for LangChain's SummarizationMiddleware in create_agent, Deep Agents and LangGraph Swarm agents. Use when agent histories outgrow the context window, tool results carry large logs, JSON or tables, summaries lose IDs, user corrections or instructions, or summarization must be validated, survive summary-model failures, be traced to its sources, or be monitored.
---

# contextsage

Use this skill for the existing `contextsage` Python package (import name
`contextsage`, Python 3.12+). It is middleware for LangChain agents, not an
agent framework, a memory store or a general parsing library.

The public API is small:

```python
from contextsage import (
    DEFAULT_IDENTIFIER_PATTERNS,
    ConfigurationError,
    IntelligentSummarizationMiddleware,
    SummarizationEvent,
)
```

The authoritative documentation is
[contextsage.readthedocs.io](https://contextsage.readthedocs.io/en/latest/),
and the source, examples and tests are at
[github.com/smuniharish/contextsage](https://github.com/smuniharish/contextsage).
Read [How it works](https://contextsage.readthedocs.io/en/latest/guide/how-it-works/)
before changing how an agent summarizes, and the
[API reference](https://contextsage.readthedocs.io/en/latest/reference/) before
using any argument this file does not show.

## Activate when

Use `contextsage` when a LangChain agent's message history must be summarized
without losing what matters. Typical indicators:

- an agent built with `create_agent`, a Deep Agents deep agent or a LangGraph
  Swarm agent whose history approaches the model's context window;
- tool or MCP results that carry long logs, JSON payloads, tables or stack
  traces;
- summaries that drop order or ticket IDs, user corrections, standing
  instructions or conflicting evidence;
- summarization that must keep working when the summary model fails, link
  each summary to its source messages, or report metrics.

Do not select it for retrieval or long-term memory, for summarizing documents
outside an agent loop, or for parsing logs in general; use parsefabric
directly for that.

## Required workflow

### Before changing an application

1. Check the installed version with `contextsage.__version__` and the
   application's dependency manifest. The package requires Python 3.12 or
   newer and LangChain 1.x agents.
2. Find the existing summarization: LangChain's `SummarizationMiddleware` in
   a `middleware=[...]` list, the summarization Deep Agents add by default, or
   hand-written trimming. ContextSage replaces it; never run two summarization
   middleware on one agent.
3. Identify the summary model, the application's ID formats, and whether the
   agent runs with a checkpointer.

### Configure

`IntelligentSummarizationMiddleware(model, ...)` takes the summary model, a
chat model or an `init_chat_model` identifier, and keyword arguments:

| Need | Argument |
| --- | --- |
| When to summarize | `trigger`: LangChain's forms, or `None` (default) to summarize when the history exceeds the token budget |
| Recent history the summary must not replace | `keep`, default `("messages", 20)` |
| A model without a LangChain profile | `maximum_context_tokens` |
| Domain IDs that must survive verbatim | `identifier_patterns=[*DEFAULT_IDENTIFIER_PATTERNS, re.compile(...)]` |
| Content formats of your own | `routes` and `fence_routes` with parsefabric parsers |
| Offline hosts or prose-heavy histories | `code_languages=()`, or a shorter tuple of grammars |
| How aggressively to compact | `policy`: `"balanced"` (default), `"maximum_preservation"` or `"maximum_compression"` |
| Metrics and alerts | `observability_hook`, a callable that receives a `SummarizationEvent` |
| Durable provenance | `provenance_store`, a langgraph-xai `ProvenanceStore` |

Invalid arguments raise `ConfigurationError` when the middleware is created.
See [Configuration](https://contextsage.readthedocs.io/en/latest/guide/configuration/).

### Integrate

- **`create_agent`**: pass the middleware in `middleware=[...]` where
  `SummarizationMiddleware` was. Sync and async agents need nothing else.
- **Deep Agents**: before `create_deep_agent(..., middleware=[...])`, call
  `register_harness_profile(provider, HarnessProfile(excluded_middleware=frozenset({"SummarizationMiddleware"})))`
  so ContextSage replaces the built-in summarization.
- **LangGraph Swarm**: add the middleware to the agents whose tool results
  grow large.

The [agent integrations guide](https://contextsage.readthedocs.io/en/latest/guide/integrations/)
and the [examples](https://github.com/smuniharish/contextsage/tree/master/examples)
show each case.

### Observe

Each rewrite emits one content-free `SummarizationEvent`, logged to the
`contextsage` logger and passed to `observability_hook`. Alert on
`recovery_status == "trimmed_fallback"` (the summary model is failing) and on
`validation_status == "failed_unrecovered"` (a tool result lost its call).
Label metrics only with these statuses, never with IDs.

## Example

```python
from itertools import cycle

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.runtime import Runtime

from contextsage import IntelligentSummarizationMiddleware, SummarizationEvent

summary = AIMessage("The user asked about a refund.")
events: list[SummarizationEvent] = []
middleware = IntelligentSummarizationMiddleware(
    model=GenericFakeChatModel(messages=cycle([summary])),
    trigger=("messages", 5),
    keep=("messages", 1),
    observability_hook=events.append,
)
history = [
    HumanMessage("Never refund more than 500 dollars without approval."),
    HumanMessage("Check the refund for order ORD-7731."),
    AIMessage("", tool_calls=[{"id": "c1", "name": "refund_log", "args": {}}]),
    ToolMessage("refund TX-3108 for ORD-7731 failed: card expired", tool_call_id="c1"),
    HumanMessage("What should we do next?"),
]
update = middleware.before_model({"messages": history}, Runtime())
print(update["messages"][1].text)
event = events[0]
print(event.validation_status, event.recovery_status)
```

Output:

```text
Here is a summary of the conversation to date:

The user asked about a refund.

Facts preserved verbatim from the earlier conversation:
- User instruction: "Never refund more than 500 dollars without approval."
- ORD-7731
- TX-3108
failed_recovered restated_facts
```

The scripted summary dropped the instruction and both IDs, so ContextSage
restated them inside the summary message. `update["messages"][0]` is the
`RemoveMessage` that replaces the old history.

## Integration rules

- Replace summarization; do not stack it.
- Keep `validation_enabled=True`; it is what guarantees that facts survive.
- In production, pass a durable `provenance_store`; the in-memory default
  keeps links until the process exits.
- Prefetch the tree-sitter grammars for offline deployments, or pass
  `code_languages=()`.
- Set a timeout on the summary model. LangChain makes up to three attempts at
  each summary call, on top of the integration's own retries; ContextSage's
  fallback applies after all of them are exhausted.
- Read API keys from the environment, never from source code.

## Prohibited shortcuts

Do **not**:

- invent imports, arguments, event fields or statuses; check the API
  reference;
- import from underscore-prefixed modules of `contextsage`;
- reimplement summarization, token counting, trimming or parsing that
  LangChain or parsefabric already provide;
- run LangChain's `SummarizationMiddleware` alongside ContextSage;
- turn validation off to silence `failed_recovered` events; improve the
  summary model or prompt instead;
- edit `src/contextsage/` when the task is an application integration.

## Verification checklist

For an application change, add a focused test that runs the middleware's
`before_model` on a representative history with a scripted chat model such as
`GenericFakeChatModel`, and asserts that the application's IDs survive in the
rewritten messages and that `validation_status` is `passed` or
`failed_recovered`. Run the project's formatter, linter, type checker and
tests.

For changes to this skill, follow the
[validation process](https://github.com/smuniharish/contextsage/blob/master/contextsage-skills/validation/README.md).
Consult the [documentation](https://contextsage.readthedocs.io/en/latest/),
[examples](https://github.com/smuniharish/contextsage/tree/master/examples) and
[tests](https://github.com/smuniharish/contextsage/tree/master/tests) rather than
expanding this file into a second manual.
