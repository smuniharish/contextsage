"""Measure the latency ContextSage adds before a model call.

Usage:
    python benchmarks/bench_middleware.py           # full run
    python benchmarks/bench_middleware.py --smoke   # quick run, as in CI

Each case runs ``IntelligentSummarizationMiddleware.before_model`` on a
synthetic history with a scripted summary model, so the timings cover parsing,
analysis, compaction, LangChain's summarization step and validation without
any network latency. A case reports the median of several runs after one
warm-up run. Each timed run uses a new middleware, so nothing is cached from
an earlier run, and, as with `timeit`, garbage collection is paused while a
run is timed.
"""

from __future__ import annotations

import argparse
import gc
import json
import statistics
import time
from dataclasses import dataclass
from itertools import cycle
from typing import TYPE_CHECKING

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langgraph.runtime import Runtime
from parsefabric.builtins import DEFAULT_CODE_LANGUAGES

from contextsage import IntelligentSummarizationMiddleware, SummarizationEvent

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


@dataclass(frozen=True, slots=True)
class Case:
    """A named history generator and the sizes to run it at."""

    name: str
    unit: str
    build: Callable[[int], list[AnyMessage]]
    sizes: Sequence[int]
    smoke_size: int
    code_languages: Sequence[str] = DEFAULT_CODE_LANGUAGES


def _tool_history(output: str) -> list[AnyMessage]:
    return [
        HumanMessage("Investigate incident INC-4410."),
        AIMessage("", tool_calls=[{"id": "c1", "name": "diagnostics", "args": {}}]),
        ToolMessage(output, tool_call_id="c1"),
        AIMessage("The diagnostics are in."),
        HumanMessage("What is the root cause?"),
    ]


def log_history(lines: int) -> list[AnyMessage]:
    """A tool result of routine log lines ending in an error."""
    log = "".join(
        f"2026-10-04T{index // 3600 % 24:02d}:{index // 60 % 60:02d}:"
        f"{index % 60:02d}Z INFO worker-{index % 4} processed batch {index}\n"
        for index in range(lines)
    )
    error = "2026-10-04T23:59:59Z ERROR connection pool exhausted for TX-991\n"
    return _tool_history(log + error)


def json_history(records: int) -> list[AnyMessage]:
    """A tool result holding a JSON array of order records."""
    orders = [
        {"sku": f"A-{index % 5}", "qty": 1 + index % 3, "state": "queued"}
        for index in range(records)
    ]
    return _tool_history(json.dumps({"service": "checkout", "orders": orders}))


def conversation_history(turns: int) -> list[AnyMessage]:
    """Many short turns, each reporting ``key=value`` facts."""
    messages: list[AnyMessage] = []
    for index in range(turns):
        messages.append(
            HumanMessage(
                f"Check request_id=req-{index} status=ok for order ORD-{index:05d}."
            )
        )
        messages.append(AIMessage(f"Request req-{index} completed normally."))
    return messages


CASES = (
    Case("tool log", "lines", log_history, (1_000, 10_000, 50_000), 200),
    Case("JSON records", "records", json_history, (1_000, 10_000), 200),
    Case("conversation", "turns", conversation_history, (100, 1_000), 20),
    Case(
        "conversation, no code detection",
        "turns",
        conversation_history,
        (1_000,),
        20,
        code_languages=(),
    ),
)


def measure(case: Case, size: int, repeat: int) -> tuple[float, SummarizationEvent]:
    """Median milliseconds of ``before_model`` over ``repeat`` runs.

    Every timed run uses a new middleware, so it analyzes the history as if
    for the first time, without results cached by an earlier run.
    """
    events: list[SummarizationEvent] = []

    def middleware() -> IntelligentSummarizationMiddleware:
        return IntelligentSummarizationMiddleware(
            model=GenericFakeChatModel(messages=cycle([AIMessage("Summary.")])),
            trigger=("messages", 4),
            keep=("messages", 2),
            code_languages=case.code_languages,
            observability_hook=events.append,
        )

    history = case.build(size)
    middleware().before_model({"messages": history}, Runtime())
    timings = []
    for _ in range(repeat):
        fresh = middleware()
        gc.collect()
        gc.disable()
        try:
            start = time.perf_counter()
            fresh.before_model({"messages": history}, Runtime())
            timings.append(time.perf_counter() - start)
        finally:
            gc.enable()
    return statistics.median(timings) * 1_000, events[-1]


def main() -> None:
    """Run every case and print a table of the results."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--smoke", action="store_true", help="run each case once at a small size"
    )
    parser.add_argument(
        "--repeat", type=int, default=5, help="timed runs per case (default 5)"
    )
    arguments = parser.parse_args()
    repeat = 1 if arguments.smoke else arguments.repeat
    header = f"{'case':<30}{'size':>16}{'tokens in':>12}{'tokens out':>12}{'ms':>10}"
    print(header)
    print("-" * len(header))
    for case in CASES:
        sizes = (case.smoke_size,) if arguments.smoke else case.sizes
        for size in sizes:
            milliseconds, event = measure(case, size, repeat)
            print(
                f"{case.name:<30}{f'{size:,} {case.unit}':>16}"
                f"{event.input_tokens:>12,}{event.output_tokens:>12,}"
                f"{milliseconds:>10,.1f}"
            )


if __name__ == "__main__":
    main()
