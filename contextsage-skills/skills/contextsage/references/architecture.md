# ContextSage architecture for agents

Use this reference to decide what ContextSage can safely handle. The
authoritative published source is the
[ContextSage documentation](https://contextsage.readthedocs.io/en/latest/);
the architecture detail is at
[Architecture - ContextSage](https://contextsage.readthedocs.io/en/latest/architecture/).

## Ownership boundary

ContextSage does not fork or reimplement semantic LLM summarization. Its
`LangGraphSummarizationAdapter` wraps LangChain's
`SummarizationMiddleware`; ContextSage owns whether to summarize and how to
prepare content, while LangGraph owns the generated semantic summary and the
`keep` cutoff.

Do not add a second semantic summarizer to compensate for this boundary.

## Verified processing model

When its trigger requires action, ContextSage:

1. observes the messages and analyzes the available budget;
2. decomposes heterogeneous content into independently classified regions;
3. scores importance and relationships;
4. derives preservation requirements and a summarization plan;
5. deterministically transforms only planner-selected compressible or
   redundant structured/log/table regions;
6. delegates semantic summarization to LangGraph;
7. validates literal must-preserve facts, tool-call/result pairing, and
   contradictory evidence;
8. recovers by restating missing preserved facts or, if the summarization
   call fails, deterministically trimming while preserving facts;
9. records lineage and emits an aggregate observability event.

Plain natural language is left for LangGraph semantic summarization.
Transformation is an optimization: if a transformer fails or does not reduce
size, the original region remains untouched.

## Content reasoning

Do not classify an entire `ToolMessage` based on one recognizable fragment.
The implementation can isolate fenced code, embedded JSON values, log-like
runs, and remaining text. Built-in structural parsers cover JSON, tables,
code, logs, and errors. Code recognition uses tree-sitter for validation;
log/error recognition is based on established grok vocabulary. Low-confidence
content remains plain text.

For an unfamiliar domain format, only consider the advanced `parsers`
constructor option after finding an existing mature parser and proving the
format needs distinct preservation treatment. The canonical
[SQL example](https://github.com/smuniharish/contextsage/tree/master/examples)
is a domain-specific example, not a mandate to add a custom parser.

## Preservation outcomes

The planner distinguishes material to preserve untouched, semantic summarize,
or deterministically transform. User corrections, active constraints,
contradiction participants, and identifiers in error context receive special
preservation treatment. This is why manually dropping old tool output is not
an equivalent solution.

See [Migration Guide - ContextSage](https://contextsage.readthedocs.io/en/latest/migration/)
for the exact differences from LangGraph's standard middleware.
