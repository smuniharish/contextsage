# Benchmarks

`bench_middleware.py` measures the latency ContextSage adds before a model
call. Each case runs the async, framework-neutral `ContextSummarizer` on a
synthetic history with a scripted parsefabric model, so timings cover parsing,
analysis, compaction, summary generation, and validation without network
latency.

```powershell
uv run python benchmarks\bench_middleware.py
uv run python benchmarks\bench_middleware.py --smoke
uv run python benchmarks\bench_middleware.py --repeat 9
```

| Case | History |
| --- | --- |
| tool log | One tool result of routine log lines that ends in an error |
| JSON records | One tool result holding a JSON array of order records |
| conversation | Many short turns, each reporting `key=value` facts |
| conversation, no code detection | The same, with `ParsingOptions(code_detector=None)` |

Every case reports the median of several timed runs after a warm-up run. Each
timed run uses a new summarizer, so it analyzes the history as if for the first
time. Results depend on the machine; the
[performance guide](https://contextsage.readthedocs.io/en/latest/operations/performance/)
lists reference numbers and tuning advice.
