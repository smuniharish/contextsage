# Migrating from SummarizationMiddleware

ContextSage accepts the arguments of LangChain's `SummarizationMiddleware`
with the same meaning, so switching is a change of import and class name:

```diff
-from langchain.agents.middleware import SummarizationMiddleware
+from contextsage import IntelligentSummarizationMiddleware

 agent = create_agent(
     model="openai:gpt-5",
     tools=tools,
     middleware=[
-        SummarizationMiddleware(
+        IntelligentSummarizationMiddleware(
             model="openai:gpt-5-mini",
             trigger=("tokens", 100_000),
             keep=("messages", 20),
         )
     ],
 )
```

## What stays the same

| Argument | Behavior |
| --- | --- |
| `model` | A chat model or `init_chat_model` identifier |
| `trigger` | Every form: `(kind, value)` tuples, clauses whose conditions must all hold, and lists of either |
| `keep` | `("messages", n)`, `("tokens", n)` or `("fraction", f)` |
| `token_counter` | Any callable that counts the tokens of a list of messages |
| `summary_prompt`, `trim_tokens_to_summarize` | Passed to LangChain unchanged |

LangChain still writes every summary, and the summary still replaces the
messages older than `keep` without separating tool calls from their results.

## What ContextSage adds

- **A budget-based default trigger.** LangChain's middleware summarizes only
  when given a `trigger`. Without one, ContextSage summarizes when the history
  no longer fits the model's context window, after reserving room for the
  response, a safety margin and overhead.
- **Compaction before the summary.** Repetitive logs, JSON and tables are
  compacted first, including large tool results in the kept messages, so the
  agent's model and the summary model read less.
- **Validation and restated facts.** Identifiers, corrections, instructions and
  conflicting values that the summary dropped are restated inside the summary.
- **A fallback.** If the summary model fails, the agent turn continues on a
  trimmed history instead of failing.
- **Provenance and events.** Every summary is linked to its sources, and
  every rewrite is reported as a `SummarizationEvent`.

## Behavior to expect

- When the trigger fires, messages can come back compacted even if none is
  old enough to summarize, because compaction applies to the whole history.
- A summary may end with a "Facts preserved verbatim from the earlier
  conversation" section when the summary model dropped facts.
- The summary message carries an ID of its own and lineage metadata, so it
  can be traced later.
