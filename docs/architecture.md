# Architecture

## Design principle

> Information preservation > raw token reduction.

A smaller summary that loses a customer ID, a user correction, or a root
cause is a failure, even if it saves tokens. ContextSage's planner is
budget-aware *and* information-aware.

## Ownership boundary

ContextSage never reimplements semantic LLM summarization. It wraps
LangChain's `SummarizationMiddleware` (`contextsage.integrations.langgraph.adapter.LangGraphSummarizationAdapter`)
and configures it with an always-eligible internal trigger. ContextSage owns
*whether* summarization runs and *what* is prepared for it; LangGraph owns
*how many* messages to keep and the actual LLM-generated summary text.

## Pipeline

```
Complete context
      |
      v
Heterogeneous context decomposition (ContextDecomposer)
      |
      v
Structural signals (StructuralSignalDetector)
      |
      v
Importance (ImportanceEngine) -> Relationships/Provenance (RelationshipEngine)
      |
      v
Preservation requirements (PreservationEngine)
      |
      v
Summarization plan (SummarizationPlanner)
      |
      v
Selective deterministic transformation (ContextTransformationEngine)
      |
      v
LangGraph semantic summarization (LangGraphSummarizationAdapter)
      |
      v
Validation (SummaryValidator) -> Recovery (RecoveryManager) if needed
      |
      v
Reconstruction (apply_transformed_units) -> Lineage/Observability/Provenance
```

See the diagrams under [docs/diagrams](https://github.com/smuniharish/contextsage/tree/main/docs/diagrams)
in the repository for rendered visuals of this pipeline and the individual
engines.

## Why context is never treated as one content type

A single `ToolMessage` (especially from an MCP server) commonly mixes
natural language, JSON, logs, errors, and metadata. `ContextDecomposer`
never classifies a whole message as one type: it extracts fenced code
blocks, then embedded JSON values (via `json.JSONDecoder.raw_decode`, which
locates a JSON value at a given start index without needing to guess the
end), then groups the remaining text into contiguous log-like vs.
plain-text runs. Each resulting region is independently classified by
`StructuralSignalDetector`, which is deliberately conservative: low
confidence means "treat as plain text" rather than risk misclassification.

Segmentation never hardcodes its own copy of "what a code fence/JSON
opener/log severity word looks like": it derives those shapes, at
construction time, from the actual `CodeParser`/`JSONParser`/`LogParser`
instances found in the detector's registry (default or overridden via
`IntelligentSummarizationMiddleware(parsers=[...])`), so there is a single
source of truth per shape instead of drifting, independently-configured
copies.

## Why deterministic transformation is an optimization, not the primary mechanism

`ContextTransformationEngine` only ever transforms units the planner
explicitly targeted as `transform_deterministic` (structured/log/table
content the preservation engine judged compressible or redundant). If a
transformer raises `TransformationError`, or the "compressed" result is not
actually smaller, the unit is left completely untouched. Ordinary natural
language is always routed to `semantic_summarize`, i.e. left for LangGraph's
own LLM-based summarization.

## Why validation and recovery exist

The planner's `preserve_untouched` classification does not force LangGraph
to literally retain a message's raw text — LangGraph's own `keep` parameter
still controls the raw/summarized cutoff. The intelligence guarantee comes
from the loop:

1. `SummaryValidator` checks the LLM-produced summary for every literal
   must-preserve fact, tool-call pairing, and unresolved contradiction.
2. If validation fails, `RecoveryManager` appends a "preserved facts"
   message restating exactly what was lost — it never re-invokes the LLM
   (which already retried transient errors internally), and never silently
   accepts an invalid summary.
3. If the LLM call itself fails (timeout, rate limit, malformed response),
   `RecoveryManager` falls back to a deterministic trim of the most recent
   `keep` messages, with a preserved-facts message prepended.

## What ContextSage is not

ContextSage is not an agent framework, memory framework, or a replacement for
LangGraph/LangChain, a general-purpose parser/document-processing
framework, or a new plugin platform — there is no public plugin registry.
See the project [README](https://github.com/smuniharish/contextsage#what-contextsage-is-not)
for the full list.
