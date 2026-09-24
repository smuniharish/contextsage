# Provenance

ContextIQ uses [`langgraph-xai`](https://pypi.org/project/langgraph-xai/) as
a direct runtime dependency to record provenance links
between the original source messages and the resulting summary, without
building or exposing a competing provenance/evidence data model.

## What is recorded

For every summarization operation, `ProvenanceManager.record_summary_provenance`
(or its async counterpart, used automatically inside `abefore_model`)
records one `ProvenanceLink` per source message that was compressed or
summarized — `source_id` is the original message's ID (never a copy of its
content, preferring references over payload duplication), `target_id` is the
summary ID, and `relation="derived_from"`. The evidence description (kind,
short summary text) is carried in the link's own `metadata` field rather
than as a separately stored `Evidence` record: `langgraph-xai`'s
`ProvenanceStore.write()` contract only accepts
`Execution | ProvenanceLink | CanonicalEvent` — `Evidence` is a value
object, not an independently storable entity — so linking directly is both
simpler and correct against every `ProvenanceStore` implementation.

This lets you answer, days later: *"where did this summary's claim about
customer 456 actually come from?"* by walking the provenance graph back to
the original message ID, even though the raw message content is long gone
from the live conversation.

## Zero user configuration

You do not need to install `langgraph-xai` yourself, register it as a
plugin, or configure a provenance store. `ProvenanceManager` uses an
in-memory `InMemoryProvenanceStore` by default. If you need durable
provenance storage in production, construct your own `ProvenanceManager`
with a store implementing `langgraph-xai`'s `ProvenanceStore` protocol
(e.g. a Postgres-backed store) and pass it via the middleware's internals —
this is an advanced/optional integration point, not required for normal
use.

## Best-effort by design

Provenance recording never aborts
or degrades summarization itself. `ProvenanceManager` methods catch all
exceptions internally and return a `ProvenanceOutcome(recorded=False,
error=...)` rather than propagating. Disable it entirely with
`provenance_enabled=False` if you don't need lineage lookups and want to
avoid even the best-effort overhead.

## Querying lineage

```python
outcome = await manager.arecord_summary_provenance(
    source_message_ids=("msg-11",),
    summary_id="summary-7",
)
links = await manager.alineage("summary-7")
```

`alineage` walks the provenance store and returns every `ProvenanceLink`
connected to the given entity ID (evidence, summary, or decision), for
example:

```
Tool Call #10 -> Tool Result #11 -> Evidence #12 -> Agent Decision #13
```
