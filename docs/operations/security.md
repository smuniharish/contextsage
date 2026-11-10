# Security and privacy

ContextSage processes conversation histories and sends the selected messages
to the summary model that the application configures. Choose model providers,
agxai stores and telemetry destinations according to your data-handling
requirements.

## Data handled

- **Summary-model input:** the history outside `keep`, after deterministic
  compaction, is sent through the configured `LanguageModel`. The provider
  determines where that request is processed.
- **Returned history:** summaries and restated facts are returned to the
  application. Summary lineage and required facts are part of the `Message`
  metadata.
- **Events:** `SummarizationEvent` contains counts, statuses, ratios, a
  thread ID and summary ID where configured. It does not contain message
  content, tool output or credentials.
- **Provenance:** agxai links contain message and summary identifiers. A
  custom store controls where those identifiers are persisted.
- **Parsing resources:** the default code detector may load grammar assets
  through parsefabric. Use `prepare()` during image build/startup or disable
  code detection when the deployment cannot load them.

## Untrusted content

User messages, tool output and retrieved documents are untrusted data.
ContextSage parses content as text and does not execute code, SQL or
commands. The summary model still receives the summarized content, so
prompt-injection text can influence generated summary text; validation
preserves required facts but is not a prompt-injection filter.

Keep custom parsers and regular expressions under application control. Treat
model output and parsed content as untrusted when using them in later
application decisions.

## Credentials and reporting

The core engine does not read provider credentials. Keep them in the provider
client's supported secret mechanism, not in message history or event labels.
The examples load live-provider settings from environment variables or a
local `.env` file.

Report vulnerabilities privately as described in the
[security policy](https://github.com/smuniharish/contextsage/blob/master/SECURITY.md).
