# Changelog

Notable changes to ContextSage are recorded here. Entries focus on released
features and improvements.

## Unreleased

Preparing version 1.0.2.

- Simplified public architecture diagrams while retaining integration,
  configuration, validation and recovery guidance.
- Corrected documentation links to repository examples and contributor guides.
- Documented independently maintained dependency and integration Agent Skills.
- Refreshed the dependency lockfile and development tooling, and documented
  maintainer-controlled manual release steps.

## [1.0.1]

- Added the asynchronous, framework-neutral `ContextSummarizer` engine and
  message adapter ABC.
- Added optional LangChain integration and kept its dependencies out of the
  core installation.
- Exposed parsefabric and agxai customization, including durable provenance
  stores and custom parsing, execution, telemetry and policy components.
- Added async lineage lookup and deletion, event sinks, OpenTelemetry
  instrumentation, examples and production documentation.
- Updated package metadata, dependency groups, examples, CI and Zensical
  documentation, with an API reference generated from the source.

[1.0.1]: https://github.com/smuniharish/contextsage/releases/tag/v1.0.1
