# How it works

ContextSage is agent middleware. LangChain calls its `before_model` hook (or
`abefore_model` in async agents) before every model call, and the hook either
leaves the history alone or returns a rewritten history that replaces it.

<figure class="diagram" markdown="span">
  ![Before a model call, ContextSage checks the trigger. If it fires, ContextSage analyzes and compacts the history. If messages are older than the keep window, LangChain writes the summary, and ContextSage checks it and restates missing facts. If the summary model fails, the history is trimmed instead.](../assets/diagrams/pipeline.png){ width="520" }
  <figcaption>One call of the middleware. Most calls stop at the trigger
  check.</figcaption>
</figure>

## 1. Trigger and budget

The middleware first counts the history's tokens with the same model-aware
counter LangChain's `SummarizationMiddleware` uses, which is calibrated by the
token usage your provider reports. If the trigger does not fire, it returns
immediately and nothing else runs.

With the default `trigger=None`, summarization runs when the history no longer
fits the input budget:

```text
available tokens = maximum_context_tokens
                 - reserved_output_tokens
                 - maximum_context_tokens × safety_margin
                 - summarization_overhead_tokens
```

For a 128,000-token model with the defaults, that is 128,000 − 4,000 − 12,800
− 2,000 = 109,200 tokens. An explicit trigger such as `("tokens", 100_000)`
fires at its own threshold instead; see [Configuration](configuration.md).

## 2. Content units

Every message is parsed with parsefabric into **content units**: runs of lines
of one kind. A tool result that mixes a heading, a JSON payload, a long log
and a stack trace becomes four units, each handled on its own terms.

| Kind | Recognized from |
| --- | --- |
| `text` | Prose and anything not recognized as another kind |
| `json` | A line that opens a JSON object or array, through its end |
| `log` | Lines with a timestamp, a leading level such as `ERROR`, or logfmt `level=` and `msg=` fields |
| `table` | Markdown and ASCII table rows |
| `code` | Fenced blocks, and unfenced code recognized by tree-sitter grammars |
| `error` | Stack traces from Python, the JVM, Node.js and Go |
| Your own | Lines claimed by a parser you route to; see [Content parsing](content-parsing.md) |

Units tile their message exactly: joining a message's units reproduces its
text byte for byte. Compaction rewrites a unit in place and leaves the rest of
the message untouched.

## 3. Importance

Each unit gets an importance score in `[0, 1]` from independent, explainable
signals:

| Signal | Weight | Counted for |
| --- | --- | --- |
| Recency | up to 0.25 | Every unit; later messages score higher |
| User correction, such as "use X instead of Y" or "no, it's X" | 0.9 | User messages |
| Standing instruction, such as "must", "never", "always" or "make sure" | 0.75 | User and system messages |
| Error severity: a stack trace or a line at `ERROR` or above | 0.35 | Every unit |
| Decision language, such as "decided", "approved" or "recommend" | 0.2 | Every unit |
| An identifier | 0.1 | Every unit |
| An identifier in a failure context | 0.35 more | Units that report or sit next to a failure |

Near-duplicate units in the middle of a run of three or more keep only a fifth
of their score, such as the same status message polled across turns.
Near-duplicates have the same kind and identifiers, and the same text apart
from timestamps, hexadecimal IDs and numbers.

User signals are only read from what users and system prompts wrote. A summary
message is sent as a user message, but the summary model wrote its text, so
its units have their own `summary` role: no correction, instruction or
user-stated identifier is read from them.

## 4. Preservation levels

The score and the policy place every unit at one of three levels:
**must preserve**, **should preserve** or **compressible**. Some units are
must-preserve whatever their score, even when they are repeated: a user
correction, an identifier the user stated, an identifier in a failure context,
and either side of a conflict. Other near-duplicates are compressible.
[Preservation policies](policies.md) lists the thresholds of each policy.

## 5. Facts

From the must-preserve units, ContextSage derives the **facts** that every
rewritten history has to contain:

- every **identifier**: UUIDs, keys such as `INC-9931`, assignments such as
  `request_id=req-7` and phrases such as `customer 456`. The identifier
  patterns are configurable;
- every **user correction**, which requires the corrected value;
- every **standing instruction**, which requires the instruction itself; and
- every **conflict**: two messages reporting different values for the same
  key, such as `status=SHIPPED` and later `status=LOST`. Both values are
  required.

A fact counts as present when its required text appears as whole words in one
message, ignoring case, whitespace and the apostrophe style, so `ORD-1` is not
satisfied by `ORD-12`. A long sentence is narrowed to the 200 characters
around its instruction or correction.

Facts outlive the messages they came from: each summary records its facts,
and every later summarization requires them again, so a correction stated
before the first summary still holds after the tenth.

Conflicts come from `key: value` and `key=value` pairs in prose and from the
top-level fields of JSON objects. Logs, stack traces, code and tables are not
searched, because differing values there record what happened over time, and
summaries are not searched, because they only repeat their sources. Keys that
naturally vary, such as IDs, timestamps, counts, sizes, latencies and log
fields like `level` and `message`, are ignored, and so is any key reported
with more than three distinct values, since it is a measurement rather than a
claim.

## 6. Compaction

Before any summary is written, structured content is compacted
deterministically:

| Content | Compaction | Allowed for |
| --- | --- | --- |
| JSON | Minified. `balanced` also collapses runs of identical items into `{"__repeated__": n, "value": item}` | Every level; lossless |
| JSON under `maximum_compression` | Identical items anywhere in a list are grouped, and long lists keep their first and last five entries around `{"__omitted__": n}` | Compressible units only |
| Tables | Runs of identical rows collapse | Every level; lossless |
| Logs | Runs of three or more lines that differ only in timestamps, hexadecimal IDs and, below `WARNING`, numbers collapse to the first line, a marker naming the omitted lines, and the last line | Compressible units only |

Lines with an identifier and blank lines never collapse. A compaction is kept
only when it makes the text shorter, and system messages and messages with
structured (non-text) content are never rewritten.

Compaction applies to the whole history, including the messages that `keep`
preserves from summarization, which is where large tool results usually are.
`keep` decides which messages the summary replaces, not which are compacted.

## 7. The summary

LangChain's `SummarizationMiddleware` writes the summary from the compacted
history, with your `keep`, `summary_prompt` and `trim_tokens_to_summarize`.
The summary replaces the messages older than the `keep` window, and never
separates a tool call from its result. Its message ID is the
`summary_id` reported in the event. When no message is old enough to
summarize but compaction shortened the history, the compacted history is
returned without a summary.

## 8. Validation, recovery and provenance

The rewritten history is checked against the facts, and missing facts are
restated verbatim inside the summary. If the summary model fails, the history
is trimmed to the `keep` window instead, and the agent turn carries on; see
[Validation and recovery](validation-recovery.md). Finally, each summarized
message is linked to the summary in a provenance store
([Provenance and lineage](provenance.md)), and a `SummarizationEvent` is
emitted ([Observability](observability.md)).

If analysis itself fails unexpectedly, ContextSage logs the error and lets
LangChain summarize the history unanalyzed, so a bug in analysis never stops
an agent.
