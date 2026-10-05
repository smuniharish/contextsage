# Validation and recovery

ContextSage does not trust the summary model to keep what matters. It checks
every rewritten history, repairs what it can, and keeps the agent running when
the summary model fails.

<figure class="diagram" markdown="span">
  ![After summarization, ContextSage checks that every must-preserve fact is present and restates missing facts in the summary, then checks that every tool result still has its tool call. When the summary model fails instead, the history is trimmed to the keep window and a notice restates the latest request and the lost facts.](../assets/diagrams/validation-recovery.png){ width="560" }
  <figcaption>Validation after a summary, and the fallback when the summary
  model fails.</figcaption>
</figure>

## What validation checks

- **Facts.** Every fact derived from the must-preserve content (identifiers,
  user corrections, standing instructions and conflicting values; see
  [How it works](how-it-works.md#5-facts)) must still appear. A fact counts
  as present when its required text appears as whole words in one message,
  ignoring case, whitespace and the apostrophe style.
- **Tool-call pairing.** Every tool result must follow the assistant message
  that requested it. LangChain's summarization never separates the two; the
  check catches anything else that rewrote the history.

## Restating missing facts

Facts the summary dropped are restated verbatim inside the summary message,
under the heading "Facts preserved verbatim from the earlier conversation".
Each fact is stated once: an identifier that a restated correction already
mentions is not repeated. Adding the facts to the summary, rather than as a
new message, keeps a valid turn order, so the history never ends with an
assistant message the model might continue.

The summary model below writes a vague summary that loses a standing
instruction, two identifiers, a correction and a conflict:

```python
--8<--
examples/preservation.py
--8<--
```

Output:

```text
--8<-- "examples/expected/preservation.txt"
```

`customer 123` is not restated on its own: the user replaced it, and the
correction records both values.

Each summary also records its facts, and every later summarization requires
them again. A correction restated in the first summary is still required, and
restated if dropped, after the messages it came from have been summarized
away.

## Statuses

Every event reports a `validation_status` and a `recovery_status`:

| Situation | `validation_status` | `recovery_status` |
| --- | --- | --- |
| The summary kept every fact | `passed` | `none_needed` |
| Facts were missing and were restated | `failed_recovered` | `restated_facts` |
| A tool result lost its tool call | `failed_unrecovered` | `none_applicable`, or `restated_facts` if facts were also restated |
| The summary model failed | `skipped` | `trimmed_fallback` |
| Validation is turned off | `disabled` | `none_needed` |

When the history only needed compaction, the status is `passed`: compaction
never removes must-preserve content. `failed_unrecovered` is also logged as a
warning that lists the tool-call IDs, because it means something outside
ContextSage broke the history.

## When the summary model fails

If the summary model raises, for example on a timeout, a rate limit or an
outage, the agent turn does not fail. Instead, ContextSage:

1. trims the history to the `keep` window with LangChain's `trim_messages`,
   starting on a user or assistant turn so no tool result is orphaned, and
   keeping a leading system message;
2. keeps the most recent tool exchange whole, even when the window would cut
   it; and
3. if the window no longer starts with a user message, or lost facts, adds a
   notice after the system messages that says what happened, repeats the
   latest user request if the window dropped it, and restates the lost facts.

```python
--8<--
examples/recovery.py
--8<--
```

Output:

```text
--8<-- "examples/expected/recovery.txt"
```

LangChain makes up to three attempts at each summary call, and provider
integrations usually retry transient errors themselves, for example through
the `max_retries` setting of `ChatOpenAI`; the fallback applies once all of
those retries are exhausted. LangGraph interrupts and other control-flow
signals are never treated as failures: they propagate unchanged.

## Turning validation off

`validation_enabled=False` skips both checks and reports `disabled`.
Summaries are then used as the model wrote them. Keep validation on unless you
validate the history yourself.
