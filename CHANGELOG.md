# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-09-23

### Added

- Initial public release of `contextsage`.
- `IntelligentSummarizationMiddleware`: a production-grade, information-aware
  replacement for LangGraph's `SummarizationMiddleware`.
- Heterogeneous context decomposition (`context/decomposition.py`) — a
  single message is split into independently-classified regions instead of
  being treated as one content type.
- Pluggable structural content parsers (JSON, table, code, log, error) via
  `ContentParser` / `ParserRegistry`, with a public `parsers` constructor
  parameter for domain-specific extensions (see `examples/sql_parser.py`).
- Budget analysis, importance scoring, relationship/dependency tracking,
  preservation classification, planning, and deterministic transformation
  engines feeding a single LangGraph summarization call.
- Post-summarization validation and staged recovery on summarization
  failure.
- Summary lineage tracking and optional `langgraph-xai` provenance
  integration.
- Structured observability events via a pluggable `ObservabilityHook`.
- Full parameter overridability: every internal default (token budget
  fractions, encoding name/timeout/cache size, classification patterns,
  parser patterns) is exposed through `IntelligentSummarizationMiddleware`'s
  public constructor — no subclassing required for common customization.
- Documentation site (`mkdocs`), requirements traceability matrix, and a
  runnable example suite (`examples/`) exercising every constructor
  parameter against a real LLM.

[Unreleased]: https://github.com/smuniharish/contextsage/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/smuniharish/contextsage/releases/tag/v0.1.0
