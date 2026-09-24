# API Reference

## Public API

The entire public surface of ContextIQ is:

```python
from contextiq import IntelligentSummarizationMiddleware
```

::: contextiq.IntelligentSummarizationMiddleware

See [Configuration](configuration.md) for every constructor parameter.

## Exceptions

`contextiq.exceptions` defines the package's exception hierarchy, all
rooted at `ContextIQError`:

- `BudgetError` / `TokenCountingError` — raised for invalid/inconsistent
  budget configuration or unrecoverable token-counting failures.
- `ClassificationError` — reserved for genuine detector bugs; ordinary
  low-confidence classification is not an error (content is simply left as
  `TEXT`).
- `PlanningError` — raised when the planner cannot produce a valid plan.
- `TransformationError` — raised internally by a deterministic transformer
  when it cannot safely compress a unit; caught by
  `ContextTransformationEngine`, which leaves the unit untouched rather than
  propagating the error.
- `SummarizationError` — raised when the underlying LangGraph summarization
  step fails; caught by the middleware and routed into `RecoveryManager`.
- `ValidationError` — raised only when a produced summary fails
  post-summarization validation and no recovery strategy can restate the
  missing facts.
- `ReconstructionError` — raised when a valid LangGraph message history
  cannot be reconstructed.
- `ProvenanceError` — raised when `langgraph-xai` provenance/evidence
  recording fails (provenance is always best-effort; this is caught and
  never aborts summarization).
- `RecoveryError` — raised when every recovery strategy has been attempted
  and failed.

## Token counting

`contextiq.budget.tokens` provides the `TokenCounter` abstract base class and
its only built-in implementation, `TiktokenTokenCounter` (wrap it in
`CachingTokenCounter` for a bounded LRU cache over raw text — this is what
`create_default_token_counter` does).

- `TiktokenTokenCounter(model=..., encoding_name=..., fallback_encoding_name=..., download_timeout_seconds=...)` —
  authoritative counting via `tiktoken` (a core dependency, no extra
  required). Pass `model` (e.g. `"gpt-4.1"`) to resolve the matching
  encoding, or `encoding_name` to bypass model-name resolution entirely. If
  no model is given, uses the universal `cl100k_base` encoding directly —
  no model-name lookup, so the zero-configuration default has no network
  dependency. If an *explicit* model-specific encoding can't be resolved
  (unrecognized name, or a network hiccup fetching an encoding that isn't
  already cached — bounded by `download_timeout_seconds`, default `5.0`, so
  this never hangs indefinitely), it falls back to `fallback_encoding_name`
  (default `cl100k_base`) — both overridable.
- `CachingTokenCounter(inner, maxsize=...)` — bounded LRU cache over raw
  text; `maxsize` defaults to `4096` and is overridable per instance.

`create_default_token_counter(model)` resolves the tokenizer to whatever
model is actually configured on the middleware and wraps it in a
`CachingTokenCounter`. Advanced integrators can implement their own
`TokenCounter` subclass (e.g. for a non-GPT-family provider's own
tokenizer) and pass it to
`IntelligentSummarizationMiddleware(token_counter=...)` — this is an
internal-but-supported extension point, not a plugin registry.

## Structural content parsers

`contextiq.parsers` provides the `ContentParser` abstract base class, a
`ParserRegistry`, and a `default_registry()` factory used by the structural
signal detector. Built-in parsers: `JSONParser`, `TableParser`, `CodeParser`,
`LogParser`, `ErrorParser`.

- `CodeParser` and `LogParser`/`ErrorParser` expose their default detection
  patterns (regexes, grok patterns, candidate tree-sitter languages,
  thresholds) as constructor keyword arguments, so an application's own log
  format or error vocabulary can be recognized without subclassing — e.g.
  `LogParser(timestamp_pattern=my_pattern, loglevel_pattern=my_levels)`.
- `CodeParser` uses [tree-sitter](https://tree-sitter.github.io/) (a core
  dependency) to validate an explicit fenced-code-block language tag, or to
  refine which language best fits text already identified as code by a
  cheap line-shape heuristic. It never blind-guesses whether ambiguous,
  untagged text is code at all — several grammars are permissive enough to
  "cleanly parse" arbitrary plain English, which would reproduce the false
  classification risk of naive lexer-guessing.
- `LogParser`/`ErrorParser` are anchored to the public, well-known
  ELK/Logstash "grok" pattern vocabulary
  (`contextiq.parsers.grok_patterns`) rather than ad hoc regexes.

This registry is an internal/advanced extension point (per the "no public
plugin architecture" design rule): ordinary `IntelligentSummarizationMiddleware`
usage never needs to construct one, but a list of custom `ContentParser`
instances can be passed directly via
`IntelligentSummarizationMiddleware(parsers=[MyParser(), ...])` for
specialized tool-output formats. Given parsers are tried, in order, *before*
the built-in ones, so a custom parser overrides detection for its own kind
while every other kind still falls back to the built-ins.

### Classification (distinct from parsing)

`contextiq.classification.signals.StructuralSignalDetector` owns a
separate, *always-on* enrichment step layered on top of whatever a parser
detected: identifier extraction, and error-keyword/severity tagging. This
applies uniformly regardless of which kind was detected, so it is
overridable independently from `parsers` (a parser decides *what kind* a
region is; this enrichment decides what to flag/extract no matter which
kind won) — via `IntelligentSummarizationMiddleware(severity_pattern=...,
error_keywords_pattern=..., identifier_patterns=...)`. Defaults:
`DEFAULT_SEVERITY_PATTERN`, `DEFAULT_ERROR_KEYWORDS_PATTERN`,
`DEFAULT_IDENTIFIER_PATTERNS` in `contextiq.classification.signals`.

## Internal engines

The following modules are internal implementation details, not part of the
supported public API (no stability guarantee across minor versions), but
are documented for contributors and for anyone extending or debugging
ContextIQ. See [`ARCHITECTURE_INTERNALS.md`](https://github.com/smuniharish/contextiq/blob/main/ARCHITECTURE_INTERNALS.md)
in the repository for a guided tour, or read the module docstrings
directly:

- `contextiq.context.decomposition.ContextDecomposer`
- `contextiq.classification.signals.StructuralSignalDetector`
- `contextiq.importance.engine.ImportanceEngine`
- `contextiq.relationships.engine.RelationshipEngine`
- `contextiq.preservation.engine.PreservationEngine`
- `contextiq.planning.planner.SummarizationPlanner`
- `contextiq.transformation.engine.ContextTransformationEngine`
- `contextiq.integrations.langgraph.adapter.LangGraphSummarizationAdapter`
- `contextiq.integrations.langgraph_xai.provenance.ProvenanceManager`
- `contextiq.validation.validator.SummaryValidator`
- `contextiq.recovery.manager.RecoveryManager`
- `contextiq.lineage.manager.LineageManager`
- `contextiq.observability.events.ObservabilityHook`
