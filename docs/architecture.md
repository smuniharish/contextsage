# Architecture

ContextSage is a thin, deterministic layer around LangChain's summarization.
It decides what the summary must not lose and checks that it did not, and
leaves the writing of summaries to LangChain.

<figure class="diagram" markdown="span">
  ![An agent calls ContextSage before each model call. The middleware checks the trigger and budget, analyzes and compacts the history, has LangChain summarize older messages, and validates the result. It returns the rewritten history and records provenance links and an event.](assets/diagrams/architecture.png){ width="720" }
  <figcaption>The middleware's stages, the services it uses, and what it
  produces.</figcaption>
</figure>

## Design principles

- **Build on the ecosystem.** LangChain writes the summaries, counts tokens and
  trims histories; parsefabric parses content; langgraph-xai stores
  provenance. ContextSage adds what they do not provide: content-aware
  analysis, compaction, validation and recovery.
- **Deterministic before generative.** Everything except the summary itself is
  deterministic: the same history and configuration always produce the same
  analysis, compaction and validation result.
- **Never fail the agent.** After construction, ContextSage recovers from model
  failures and logs everything else, so summarization cannot break an agent
  turn. Configuration errors surface early, when the middleware is created.
- **Content-free telemetry.** Events and log records describe what happened in
  counts and statuses, never with message content.
- **Bounded work.** Patterns run in linear time on untrusted text, and conflict
  detection stays linear in the size of the history.

## Components

| Component | Responsibility |
| --- | --- |
| Trigger and budget | Counts tokens with LangChain's counter and decides whether to run, from the trigger or the input budget |
| Parser | parsefabric's `MixedContentParser`, configured with ContextSage's log, stack-trace, table and JSON recognition and your routes |
| Analysis | Splits messages into content units, scores their importance, finds conflicting values, assigns preservation levels and derives facts |
| Compaction | Rewrites JSON, tables and logs deterministically within what each unit's level allows, and rebuilds each message |
| Summarizer | LangChain's `SummarizationMiddleware`, which writes the summary of the messages older than `keep` |
| Validation and recovery | Checks facts and tool-call pairing, restates missing facts, and trims the history when the summary model fails |
| Provenance | Writes a `derived_from` link per replaced message to a langgraph-xai store, and answers lineage queries |
| Events | Builds the `SummarizationEvent`, logs it and passes it to the hook |

[How it works](guide/how-it-works.md) follows a history through these
components step by step.

## Guarantees

The test suite checks each of these, many with property-based tests over
generated histories:

- Content units tile each message exactly, so content that is not compacted
  stays byte for byte as it was.
- Compaction never makes content longer, and never touches system messages or
  messages with structured content.
- Compaction never removes a fact: facts come from must-preserve content, which
  receives only lossless compaction.
- After a summary, every fact is present, either kept by the summary model or
  restated, and facts stay required in every later summary.
- Text the summary model wrote never becomes a user instruction or
  correction.
- The fallback never starts the history on a tool result, and never separates
  the latest tool call from its result.
- Lossy JSON compaction never invents values.

## Public API and versioning

The public API is everything listed in the [API reference](reference/index.md)
and exported by the `contextsage` package. Modules and names that start with
an underscore are internal and can change in any release. ContextSage follows
[Semantic Versioning](https://semver.org/).
