# Security and privacy

ContextSage reads the agent's conversation to decide what to keep. This page
describes what it does with that content, what leaves the process, and how it
treats untrusted input.

## What leaves the process

- **The summary request.** Messages older than the `keep` window, after
  compaction, are sent to the summary model through its LangChain
  integration, exactly as with LangChain's own summarization. Choose a model
  and provider that may receive your conversation data.
- **Grammar downloads.** tree-sitter-language-pack downloads code-detection
  grammars the first time they are needed. Prefetch them while building your
  image to run without outbound access; see
  [Installation](../getting-started/installation.md#code-detection-grammars).

ContextSage makes no other network calls.

## What is stored and logged

- **The rewritten history** goes back into the agent state, and into your
  checkpointer if you use one, like any other state update. Restated facts are
  verbatim copies of text that was already in the history. Each summary
  message also records the facts it had to keep in its `additional_kwargs`,
  so they stay required in later summaries; like the rest of the message, this
  record is stored in the agent state.
- **Events** contain counts, ratios, statuses and IDs, never message content.
- **Log records** contain the same, plus summary and tool-call IDs. Warnings
  about a failed summary model, provenance store or hook include the exception
  and its message, which come from those components; route the `contextsage`
  logger accordingly.
- **Provenance links** contain message, summary and thread IDs and no content.

## Untrusted content

Tool results, web pages and user messages are untrusted input.

- **Parsing never executes anything.** Code, SQL and commands are recognized
  from their text only.
- **Patterns run in linear time.** The built-in patterns use bounded or
  possessive quantifiers and no overlapping repetition, so crafted input
  cannot cause catastrophic backtracking; the test suite runs each pattern
  that sees unbounded input on pathological text. Keep your own
  `identifier_patterns` and `routes` linear-time as well.
- **Work is bounded.** Analysis is linear in the size of the history, and
  conflict detection tracks at most three values per key. In async agents,
  analysis runs in a worker thread, so it never blocks the event loop.
- **Tool output cannot create instructions.** Standing instructions are only
  taken from user and system messages, and corrections only from user
  messages. Summaries are never read for either, because the summary model
  wrote them. So text inside a tool result cannot add a "User instruction" or
  "User correction" to the summary, even when the summary model repeats it.

The summary model still reads the summarized messages, including tool output,
so a prompt injection in a tool result can influence the summary text, as it
can with any summarization. Validation only adds required facts; it does not
remove what the model wrote.

## Trusted configuration

The middleware's arguments are trusted: custom parsers and routes run in your
process, and identifier patterns run on every message. Load them only from
code you control.

## Credentials

ContextSage never reads credentials. The summary model's integration handles
them. The examples read their API key from the environment or from a `.env`
file, which the repository's `.gitignore` excludes.

## Report a vulnerability

Report vulnerabilities privately, as described in the
[security policy](https://github.com/smuniharish/contextsage/blob/master/SECURITY.md).
