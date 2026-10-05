# Performance

ContextSage adds work before model calls. This page shows where the time
goes, gives reference numbers, and lists what to tune.

## Where the time goes

- **Calls that do not trigger** only count the history's tokens with
  LangChain's approximate counter: about 1 ms for a 2,000-message history.
  Most model calls end here.
- **Calls that trigger** parse and analyze the whole history, compact it,
  call the summary model and validate the result. Without the summary call,
  the cost is linear in the size of the history. The summary call usually
  dominates, but it is not part of the numbers below.

## Reference numbers

`benchmarks/bench_middleware.py` measures triggered calls with a scripted
summary model, so the numbers show ContextSage's own work. Every run analyzes
the history for the first time. Medians of seven runs, with Python 3.14 on a
13th-generation Intel Core i9 laptop:

| History | Size | Tokens | Latency |
| --- | --- | --- | --- |
| Tool result with a long log | 1,000 lines | 13,799 | 28 ms |
| | 10,000 lines | 139,799 | 234 ms |
| | 50,000 lines | 709,799 | 1.28 s |
| Tool result with a JSON array | 1,000 records | 11,320 | 23 ms |
| | 10,000 records | 112,570 | 203 ms |
| Conversation of short turns | 100 turns | 3,200 | 200 ms |
| | 1,000 turns | 32,000 | 1.91 s |
| The same, with `code_languages=()` | 1,000 turns | 32,000 | 215 ms |

Logs and JSON cost about 25 µs per line or record. Prose costs about 1 ms per
message with the default grammars, almost all of it in code detection: each
new block of prose is tried against up to nine tree-sitter grammars before it
is accepted as prose. In the conversation cases every user turn states two
new IDs, all of which must survive, so the rewritten history restates about
2,000 identifiers for 1,000 turns.

Run the benchmark on your own hardware with:

```bash
uv run python benchmarks/bench_middleware.py
```

## What to tune

- **Code detection.** parsefabric caches detection results for short texts in
  each middleware, so a message is usually detected once in its lifetime: when
  the first summarization after it arrives. For histories of mostly prose,
  where code arrives in fenced blocks, `code_languages=()` removes nearly all
  of the cost, and a shorter list such as `("python", "sql")` removes most of
  it. See [Content parsing](../guide/content-parsing.md#code-detection).
- **Trigger.** Each summarization analyzes the whole history, so summarizing
  less often costs less in total. A higher threshold, or the budget-based
  default, summarizes less often than a low message count.
- **Token counting.** The default counter is fast. An exact counter, such as
  a model's `get_num_tokens_from_messages`, runs before every model call and
  costs more on long histories.
- **Hooks.** The observability hook runs inline; keep it fast and move exports
  to a queue.
- **Async agents.** The asynchronous hook analyzes the history in a worker
  thread, so other coroutines keep running; the summary call itself is
  asynchronous.

## Memory

Analysis holds the content units of the history while a call runs; nothing is
kept between calls except parsefabric's bounded detection cache. The default
in-memory provenance store keeps every link until the process exits, so use a
durable store in long-running processes; see
[Provenance and lineage](../guide/provenance.md#choose-a-store).
