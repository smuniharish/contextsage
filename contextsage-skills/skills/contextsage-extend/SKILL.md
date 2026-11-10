---
name: contextsage-extend
description: >-
  Use this skill when extending ContextSage with a custom agent
  FrameworkAdapter, parsefabric LanguageModel, Tokenizer, parser, JSON codec,
  execution backend, or lifecycle sink; a ContextSage TokenCounter,
  PreservationPolicy, or EventSink; or an agxai ProvenanceStore, provider,
  plugin, or capture policy. Also use it to test or debug one of those
  components. Use contextsage for normal integration and configuration. Do
  not use it to build an agent framework, retrieval system, or memory API.
license: Apache-2.0
compatibility: >-
  Python 3.12 or newer with contextsage 1.x installed. Install
  contextsage[langchain] only when the adapter integrates LangChain.
metadata:
  version: "1.0.1"
  documentation: "https://contextsage.readthedocs.io/en/latest/guide/integrations/"
---

# Extending ContextSage

ContextSage keeps framework and provider choices at explicit extension
boundaries. Implement the existing abstract base class for the component you
need; do not add a parallel extension interface.

## Choose the boundary

| Requirement | Component |
| --- | --- |
| Adapt messages from Agno, CrewAI or an in-house loop | `FrameworkAdapter[NativeT]` |
| Generate summaries | parsefabric `LanguageModel` passed to `ContextSummarizer` |
| Count tokens | ContextSage `TokenCounter`, or parsefabric `Tokenizer` with `TokenizerTokenCounter` |
| Change content recognition | parsefabric `Pattern`, `Parser`, `JSONCodec`, `CodeDetector` and `ParsingOptions` |
| Change parsing execution or lifecycle telemetry | parsefabric `ExecutionBackend` or `ObservabilitySink` in `ParsingOptions` |
| Change importance and JSON compaction | ContextSage `PreservationPolicy` |
| Export summary events | ContextSage `EventSink` |
| Persist summary lineage | agxai `ProvenanceStore`, registered through `create_agxai_runtime` |
| Change other agxai capabilities | `ObservabilityProvider`, `AttributionEngine`, `ExplanationEngine`, `PolicyProvider`, `CapturePolicy`, `XAIPlugin`, or custom state capture |

The [integration guide](https://contextsage.readthedocs.io/en/latest/guide/integrations/)
documents the available customizations and the
[downstream example](https://github.com/smuniharish/contextsage/blob/master/examples/downstream_customization.py)
demonstrates implementations.

## Workflow

1. Confirm the installed ContextSage, parsefabric and agxai versions. Read the
   public ABC and constructor signature from those versions before writing
   methods.
2. Implement only the selected boundary. Keep async methods async, propagate
   cancellation, and let validation failures surface at configuration time.
3. For a `FrameworkAdapter`, preserve native messages when unchanged and
   store summary `lineage` in framework metadata or checkpoint state.
4. For a custom store, implement agxai's `ProvenanceStore` ABC and follow its
   store contract. Pass it to `create_agxai_runtime(store=...)`; ContextSage
   does not define a separate database-store API.
5. Add contract-focused tests using a disposable store or scripted component.
   Test close/flush ownership, ordering, retries and failure behavior where
   they apply.
6. Run targeted tests, Ruff, Pyrefly and the relevant example. Update docs
   and this package's skill only for verified behavior.

## Adapter invariants

- Convert only the fields needed by `contextsage.Message`; preserve tool-call
  IDs, roles, message IDs and stable framework metadata.
- Set `Message.native` to the source object so unchanged messages can be
  reused.
- Convert new summary and recovery messages back to native messages.
- Propagate framework control-flow exceptions through
  `FrameworkAdapter.propagated_errors`.
- Preserve `SummaryLineage` across checkpoints to keep later generations
  connected.

## Dependency-component invariants

- Follow the exact dependency ABC. Do not use structural typing in place of
  the documented subclass.
- Keep ContextSage event sinks and parsefabric lifecycle sinks distinct; they
  receive different event models.
- Configure agxai through `create_agxai_runtime` so component type checks and
  registration remain consistent.
- Keep data-minimization and error behavior explicit. Events must not contain
  conversation content or credentials.

## Verification

The repository's [downstream customization example](https://github.com/smuniharish/contextsage/blob/master/examples/downstream_customization.py)
exercises a custom tokenizer, parser lifecycle sink, execution backend,
agxai store, capture policy and observability provider. Use the
[testing guide](https://contextsage.readthedocs.io/en/latest/development/testing/)
for test commands and the
[API reference](https://contextsage.readthedocs.io/en/latest/reference/)
for public signatures.
