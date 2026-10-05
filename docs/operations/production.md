# Production checklist

ContextSage works with its defaults, but a production deployment should make
a few choices deliberately.

## Configuration

- [ ] **Summary model.** Use a fast, reliable model and set a `timeout` on it.
  LangChain makes up to three attempts at each summary call, each with your
  provider integration's own retries (for example `max_retries` on
  `ChatOpenAI`), so keep those modest; the fallback takes over once all
  retries are exhausted.
- [ ] **Context window.** Check that `available_tokens` in the events matches
  your model. If the model has no LangChain profile, set
  `maximum_context_tokens`.
- [ ] **Trigger.** Summarize early enough that the summary call itself fits:
  either rely on the budget (`trigger=None`) or set a threshold below it.
- [ ] **Keep window.** Make `keep` large enough to hold the working set of the
  current task, such as the latest tool exchanges.
- [ ] **Identifiers.** Add patterns for your domain's IDs to
  `DEFAULT_IDENTIFIER_PATTERNS`, so that they survive every summary.
- [ ] **Policy.** Start with `balanced`; see
  [Preservation policies](../guide/policies.md).

## Deployment

- [ ] **Grammars.** Download the code-detection grammars while building your
  image, or narrow `code_languages`; see
  [Installation](../getting-started/installation.md#code-detection-grammars).
- [ ] **Provenance store.** Replace the in-memory default with a durable
  `ProvenanceStore`, which also keeps memory use flat in long-running
  processes; see [Provenance and lineage](../guide/provenance.md#choose-a-store).
- [ ] **Versions.** Pin ContextSage and its dependencies with a lock file,
  and read the [changelog](../changelog.md) before upgrading.

## Monitoring

- [ ] **Metrics.** Export events from the `observability_hook`; see
  [Observability](../guide/observability.md#metrics).
- [ ] **Alerts.** Alert on the rate of `trimmed_fallback` (the summary model is
  failing) and on any `failed_unrecovered` (something outside ContextSage
  broke a tool exchange). A steady rate of `failed_recovered` means the summary
  model often drops facts; a better prompt or model reduces it.
- [ ] **Logs.** Route `WARNING` and `ERROR` records of the `contextsage` logger
  to your log pipeline.

## Testing

- [ ] **Test your configuration offline.** Run the middleware on
  representative histories with a scripted model, as the
  [examples](../examples.md) do, and assert on the events. This catches
  identifiers that are not recognized and triggers that never fire, without
  calling a model.
