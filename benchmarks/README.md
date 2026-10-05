# Benchmarks

`bench_middleware.py` measures the latency ContextSage adds before a model
call. Each case runs `IntelligentSummarizationMiddleware.before_model` on a
synthetic history with a scripted summary model, so the timings cover parsing,
analysis, compaction, LangChain's summarization step and validation, without
network latency.

```bash
uv run python benchmarks/bench_middleware.py            # full run
uv run python benchmarks/bench_middleware.py --smoke    # quick run, as in CI
uv run python benchmarks/bench_middleware.py --repeat 9 # more timed runs
```

| Case | History |
| --- | --- |
| tool log | One tool result of routine log lines that ends in an error |
| JSON records | One tool result holding a JSON array of order records |
| conversation | Many short turns, each reporting `key=value` facts |
| conversation, no code detection | The same, with `code_languages=()` |

Every case reports the median of several timed runs after a warm-up run. Each
timed run uses a new middleware, so it analyzes the history as if for the first
time, and garbage collection is paused while a run is timed, as `timeit` does.
Results depend on the machine; the
[performance guide](https://contextsage.readthedocs.io/en/latest/operations/performance/)
lists reference numbers and tuning advice.
