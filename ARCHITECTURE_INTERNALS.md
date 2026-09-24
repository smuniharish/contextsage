# Architecture internals

> **Internal engineering artifact.** This is a guided tour of ContextIQ's
> internal pipeline stages/classes, kept for contributors and maintainers
> debugging summarization behavior. It is intentionally **not** part of the
> published documentation site (`docs/`) — per the project's design
> principle, users of `IntelligentSummarizationMiddleware` should never
> need to know about `ContextUnit`, engines, or any of the internals below
> to use the package. See [`docs/architecture.md`](docs/architecture.md)
> for the user-facing architecture overview, and
> [`docs/api-reference.md`](docs/api-reference.md) for the supported
> public surface.

This page is a guided tour of ContextIQ's internal pipeline stages. These
classes are implementation details (see the module docstrings, or
`docs/api-reference.md`) but are documented for contributors and anyone
debugging summarization behavior.

## `ContextObserver`

`contextiq.context.observer.ContextObserver` — the entry point. Counts
tokens for the full incoming message list and produces an observation used
by the budget analyzer; this is the cheapest possible pre-check so the
expensive pipeline stages below only run when actually needed.

## `BudgetAnalyzer`

`contextiq.budget.analyzer.BudgetAnalyzer` implements an explicit,
inspectable budget model:

```
maximum_context_tokens
reserved_output_tokens
system_tokens
tool_schema_tokens
current_input_tokens
safety_margin_tokens
available_input_tokens
overflow_tokens
```

`infer_max_context_tokens(model)` looks up known context-window sizes for
common providers/models, falling back to a conservative default when the
model is unrecognized.

## `ContextDecomposer`

`contextiq.context.decomposition.ContextDecomposer` converts a heterogeneous
message list into a flat list of `ContextUnit`s. It never
treats one message as one content type:

1. Fenced code blocks (`` ``` ``) are extracted as `CODE` regions.
2. Embedded JSON values inside the remaining text are located with
   `json.JSONDecoder.raw_decode`, which can find a JSON value starting at a
   given index without needing to pre-guess where it ends.
3. Remaining text is segmented into contiguous log-like vs. plain-text runs.

## `StructuralSignalDetector`

`contextiq.classification.signals.StructuralSignalDetector`
assigns a `RegionKind` (or custom string kind — see below) and a confidence
score to each unit, plus lightweight `ContentSignals` (identifiers found,
whether an error/severity marker is present, table-likeness, etc.).
Detection is conservative by design: e.g. log-line detection requires a
leading timestamp pattern, so unlabeled plain text is never misclassified
as a log purely because it contains the word "error".

Kind-detection itself is delegated to a pluggable
`contextiq.parsers.ParserRegistry` — an ordered collection of
`ContentParser` implementations, tried in turn, first non-`None` result
wins. The built-in registry (`default_registry()`) contains:

1. `JSONParser` / `TableParser` — the most structurally unambiguous, so
   they run first.
2. `CodeParser` — fenced code blocks are trusted directly; a stated
   language tag or a line-shape heuristic match is then *validated/refined*
   with real `tree-sitter` parsing (a core dependency), never blind-guessed.
3. `LogParser` / `ErrorParser` — anchored to the public ELK/Logstash "grok"
   pattern vocabulary (`contextiq.parsers.grok_patterns`) rather than ad hoc
   regexes; `ErrorParser` runs last since it deliberately overlaps with
   ERROR-severity log lines.

Every built-in parser's default patterns/thresholds are overridable via
constructor keyword arguments (e.g. `LogParser(timestamp_pattern=...)`),
and a fully custom `ParserRegistry` can be passed to
`StructuralSignalDetector(registry=...)` — an internal-but-supported
extension point, not a public plugin-registration API.

## `ImportanceEngine`

`contextiq.importance.engine.ImportanceEngine` computes a
composite, bounded `[0, 1]` importance score per unit from independent
signals — recency, user corrections, active constraints, decision language,
error severity, identifiers (especially identifiers co-occurring with an
error), and repetition-group membership. Every contribution is recorded in
a `reasons` tuple so behavior is auditable and testable, not an opaque
score.

## `RelationshipEngine`

`contextiq.relationships.engine.RelationshipEngine`
detects `Relationship`s between units: `CONTRADICTS` (same key, conflicting
values, e.g. two RAG sources disagreeing), `CORRECTED_BY` (a user
correction referencing an earlier value), and tool-call pairing via
`pair_tool_calls` (an `AIMessage`'s `tool_calls` matched to their
`ToolMessage` results by `tool_call_id`), which the planner and validator
use to keep AI-tool-call / tool-result pairs intact together.

## `PreservationEngine`

`contextiq.preservation.engine.PreservationEngine` converts
importance + relationships into an explicit `PreservationLevel`
(`MUST_PRESERVE`, `SHOULD_PRESERVE`, `COMPRESSIBLE`, `REDUNDANT`,
`SAFE_TO_DROP`) per unit, and extracts concrete literal
`must_preserve_facts` (identifiers, correction referents, constraint
sentences) that `SummaryValidator` later checks the produced summary text
for. Its thresholds are tunable via the `policy` constructor argument
(`"balanced"` / `"maximum_preservation"` / `"maximum_compression"`) — see
[`docs/configuration.md`](docs/configuration.md#policies). Certain reasons (user
correction, contradiction participant, identifier-in-error-context) are
*always* `MUST_PRESERVE` regardless of policy, because they are
structurally important, not just numerically important.

## `SummarizationPlanner`

`contextiq.planning.planner.SummarizationPlanner` is the
core intelligence: given classified units, it decides which units become
`transform_deterministic` targets (structured/log/table content with a
compressible/redundant preservation level), which are routed to
`semantic_summarize` (left for the LLM), and which are `preserve_untouched`
(must/should-preserve content, or content belonging to a protected
message).

## `ContextTransformationEngine`

`contextiq.transformation.engine.ContextTransformationEngine`
applies per-kind deterministic transformers
(`contextiq.transformation.logs.reduce_log_block` for repetitive/verbose log
blocks, `contextiq.transformation.structured.compact_json` for JSON) only to
units the planner explicitly targeted. If a transformer raises
`TransformationError`, or produces a result that isn't actually smaller, the
unit is left completely untouched — deterministic transformation is always
an optimization, never a requirement.

## `LangGraphSummarizationAdapter`

`contextiq.integrations.langgraph.adapter.LangGraphSummarizationAdapter`
wraps LangChain's `SummarizationMiddleware` directly — it
does not fork it or reimplement LLM summarization. It configures the
wrapped middleware with an always-eligible trigger (ContextIQ has already
decided summarization is required upstream) and the user's `keep`
parameter, then invokes its `before_model`/`abefore_model` hooks against
the prepared (post-transformation) message list.

## `SummaryValidator`

`contextiq.validation.validator.SummaryValidator` checks
the produced summary text for every literal must-preserve fact, for tool
call/result pairing integrity, and for contradiction survival (both
conflicting values must be simultaneously discoverable — a summary that
silently drops both sides of a contradiction, or collapses to just one
side, fails validation just as surely as one that fabricates false
certainty).

## `RecoveryManager`

`contextiq.recovery.manager.RecoveryManager` implements
the staged recovery process: on validation failure, it restates missing
facts in an appended message without re-invoking the LLM; on a hard
summarization failure (timeout, malformed response, rate limit), it falls
back to a deterministic trim of the most recent `keep` messages with a
preserved-facts message prepended, and never silently discards
`MUST_PRESERVE` content.

## `LineageManager`

`contextiq.lineage.manager.LineageManager` records a
`SummaryLineage` per operation (source unit/message IDs, generation number,
token counts, compression ratio, validation/recovery/fallback status) and
`find_prior_summary_ids` walks prior `RemoveMessage`/summary markers so a
summary-of-a-summary retains lineage back to its original sources, rather
than degrading silently across repeated summarizations.

## `ObservabilityHook`

`contextiq.observability.events.ObservabilityHook` is the
structured-events interface. `LoggingObservabilityHook` (default) logs a
`SummarizationEvent` per operation at `INFO` level — trigger reason, token
counts, selected targets, compression ratio, validation/recovery/fallback
status, latency — and never logs raw message content. `NullObservabilityHook`
disables this. Supply your own `ObservabilityHook` implementation to forward
events to your own telemetry system.
