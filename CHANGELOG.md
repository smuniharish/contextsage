# Changelog

All notable changes to ContextSage are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-10-05

ContextSage 1.0 is a rewrite on top of parsefabric, LangChain and
langgraph-xai. Only the `IntelligentSummarizationMiddleware` class and its
LangChain-compatible arguments carry over from 0.1; there is no compatibility
layer for the 0.1 internals.

### Added

- Content parsing with [parsefabric](https://pypi.org/project/parsefabric/):
  every message is split into prose, JSON, log, table, code and stack-trace
  units that tile the message exactly. The `routes`, `fence_routes` and
  `code_languages` arguments add your own formats and choose the code-detection
  grammars.
- Compaction of large tool results at any position in the history: runs of
  similar log lines collapse to their first and last line around a marker
  naming the omitted lines, identical JSON items and table rows are counted,
  and JSON is minified. Must-preserve content only receives lossless
  compaction.
- Facts that every rewritten history must keep: identifiers, user corrections,
  standing instructions and conflicting values. Missing facts are restated
  verbatim inside the summary message, each fact once. Facts are matched as
  whole words, ignoring case, whitespace and the apostrophe style, and each
  summary records its facts so that later summaries keep them too.
- A fallback when the summary model fails: the history is trimmed with
  LangChain's `trim_messages` without orphaning a tool result, and a notice
  restates the latest user request and the lost facts.
- Provenance with [langgraph-xai](https://pypi.org/project/langgraph-xai/):
  each summarized message is linked to its summary in a `ProvenanceStore`
  (`provenance_store`), summaries record their generation, and `alineage`
  returns the lineage of a summary across generations.
- `SummarizationEvent` reports compaction, preservation, content kinds, token
  budget, validation and recovery for every rewrite, without message content.
- `DEFAULT_IDENTIFIER_PATTERNS`, so domain patterns can extend the built-in
  ones.
- Summary-model tokens are kept out of `stream_events(version="v3")` message
  streams.
- Support for Python 3.14, offline and live examples with recorded output,
  benchmarks, and an Agent Skill for coding agents.

### Changed

- Tokens are counted with the counter LangChain's `SummarizationMiddleware`
  uses for the model, calibrated by the usage the provider reports, instead of
  tiktoken.
- `trigger` accepts every LangChain form, including clauses and lists, and
  defaults to summarizing when the history exceeds the token budget.
- `keep=("fraction", f)` is a share of `maximum_context_tokens`, so it also
  works for models without a LangChain profile.
- The asynchronous hook analyzes the history in a worker thread instead of on
  the event loop.
- `observability_hook` is a plain callable that receives a
  `SummarizationEvent`, and events are logged to the `contextsage` logger.
- Configuration errors raise `ConfigurationError`, which is a `ValueError`,
  when the middleware is created.

### Removed

- The 0.1 content-parser registry and the `parsers`, `severity_pattern` and
  `error_keywords_pattern` arguments; use parsefabric `routes` and
  `fence_routes` instead.
- The `observability_enabled` and `provenance_enabled` arguments. Events are
  always logged, and provenance always goes to the configured store.
- The tiktoken dependency.

## [0.1.0] - 2026-09-23

### Added

- Initial public release of `contextsage`.
- `IntelligentSummarizationMiddleware`: an information-aware replacement for
  LangChain's `SummarizationMiddleware`.
- Decomposition of a single message into independently classified regions.
- Pluggable structural content parsers for JSON, tables, code, logs and
  errors.
- Budget analysis, importance scoring, relationship tracking, preservation
  classification and deterministic transformation before LangChain's
  summarization call.
- Post-summarization validation and staged recovery.
- Summary lineage tracking and optional langgraph-xai provenance.
- Structured observability events through a pluggable hook.

[Unreleased]: https://github.com/smuniharish/contextsage/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/smuniharish/contextsage/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/smuniharish/contextsage/releases/tag/v0.1.0
