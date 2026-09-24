# Migration from LangGraph's `SummarizationMiddleware`

`IntelligentSummarizationMiddleware` is designed to be a near drop-in
replacement:

```diff
-from langchain.agents.middleware.summarization import SummarizationMiddleware
+from contextiq import IntelligentSummarizationMiddleware

-middleware = SummarizationMiddleware(
+middleware = IntelligentSummarizationMiddleware(
     model=model,
     trigger=("tokens", 100_000),
     keep=("messages", 20),
 )
```

## What is preserved exactly

- The `trigger=("tokens", N)` / `("messages", N)` / `("fraction", f)`
  configuration shape (`contextiq.planning.trigger.TriggerSpec`).
- The `keep=` configuration shape and semantics — it is forwarded directly
  to LangGraph's `SummarizationMiddleware`, unchanged.
- `summary_prompt` and `trim_tokens_to_summarize` — forwarded directly.
- Sync (`before_model`) and async (`abefore_model`) support.
- The actual LLM-generated summary text and its position in the message
  list — ContextIQ never rewrites what the LLM produces; it only prepares
  the input and validates/recovers the output.

## What is different

- **`trigger=None` behavior**: LangGraph requires an explicit trigger.
  ContextIQ allows omitting `trigger` entirely, in which case its own
  `BudgetAnalyzer` decides purely from overflow against the model's context
  window — there is no equivalent in vanilla LangGraph.
- **Internal LangGraph trigger is always "eligible"**: ContextIQ configures
  the *wrapped* `SummarizationMiddleware` with an always-eligible internal
  trigger (`("tokens", 1)`), because ContextIQ's own planner — not
  LangGraph's trigger clause — is the sole authority on *whether*
  summarization runs. This is an
  implementation detail and does not change observable `trigger=`
  behavior from the caller's perspective.
- **Selective preparation before the LLM ever sees the content**: unlike
  vanilla `SummarizationMiddleware`, which sends whatever falls before the
  `keep` cutoff straight to the LLM, ContextIQ decomposes, scores, and may
  deterministically compress structured/log content *before* invoking
  LangGraph's summarization step — the LLM call itself may receive less
  (but strictly not less *important*) input.
- **Post-summarization validation and recovery**: vanilla
  `SummarizationMiddleware` returns whatever the LLM produces. ContextIQ
  validates the result and, on failure, appends a preserved-facts message
  or falls back to a deterministic trim — this is new behavior with no
  vanilla equivalent, and can occasionally result in an extra message in
  the output that vanilla LangGraph would not have produced.
- **New parameters** with no vanilla equivalent: `policy`,
  `maximum_context_tokens`, `reserved_output_tokens`, `safety_margin`,
  `validation_enabled`, `observability_enabled`, `observability_hook`,
  `provenance_enabled`, `token_counter`.

## What is intentionally *not* replicated

LangGraph's `SummarizationMiddleware` supports an arbitrarily complex
`TriggerClause` combinator (boolean AND/OR compositions of trigger
conditions). ContextIQ's public `trigger=` parameter supports the three
common single-condition forms (`tokens`, `messages`, `fraction`) plus
`None`; it does not currently expose LangGraph's full combinator syntax.
This is a deliberate simplification in service of keeping the public API
extremely simple — most real-world usage does not need boolean trigger
composition, and the budget-analyzer-driven `trigger=None` mode already
covers the most common reason to want anything beyond a single condition
("summarize whenever it wouldn't fit").
