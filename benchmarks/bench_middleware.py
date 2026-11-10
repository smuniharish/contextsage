"""Measure the latency ContextSage adds before a model call.

Usage:
    python benchmarks/bench_middleware.py           # full run
    python benchmarks/bench_middleware.py --smoke   # quick run, as in CI

Each case runs the async, framework-neutral ``ContextSummarizer`` on a
synthetic history with a scripted parsefabric model, so timings cover parsing,
analysis, compaction, summary generation and validation without network
latency. A case reports the median of several runs after one warm-up run.
Each timed run uses a new summarizer, so nothing is cached from earlier runs.
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import json
import statistics
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from parsefabric import LanguageModel

from contextsage import ContextSummarizer, Message, ParsingOptions, SummarizationEvent, ToolCall

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from parsefabric import ChatMessage


class ScriptedModel(LanguageModel):
    """Return one fixed summary without network access."""

    @override
    async def complete(self, messages: Sequence[ChatMessage]) -> str:
        return "Summary of the conversation."


@dataclass(frozen=True, slots=True)
class Case:
    """A named history generator and the sizes to run it at."""

    name: str
    unit: str
    build: Callable[[int], list[Message]]
    sizes: Sequence[int]
    smoke_size: int
    code_detection: bool = True


def _tool_history(output: str) -> list[Message]:
    return [
        Message("user", "Investigate incident INC-4410."),
        Message("assistant", "", tool_calls=(ToolCall("c1", "diagnostics", {}),)),
        Message("tool", output, tool_call_id="c1"),
        Message("assistant", "The diagnostics are in."),
        Message("user", "What is the root cause?"),
    ]


def log_history(lines: int) -> list[Message]:
    """A tool result of routine log lines ending in an error."""
    log = "".join(
        f"2026-10-04T{index // 3600 % 24:02d}:{index // 60 % 60:02d}:"
        f"{index % 60:02d}Z INFO worker-{index % 4} processed batch {index}\n"
        for index in range(lines)
    )
    return _tool_history(log + "2026-10-04T23:59:59Z ERROR connection pool exhausted for TX-991\n")


def json_history(records: int) -> list[Message]:
    """A tool result holding a JSON array of order records."""
    orders = [
        {"sku": f"A-{index % 5}", "qty": 1 + index % 3, "state": "queued"}
        for index in range(records)
    ]
    return _tool_history(json.dumps({"service": "checkout", "orders": orders}))


def conversation_history(turns: int) -> list[Message]:
    """Many short turns, each reporting ``key=value`` facts."""
    messages = []
    for index in range(turns):
        messages.extend(
            (
                Message(
                    "user",
                    f"Check request_id=req-{index} status=ok for order ORD-{index:05d}.",
                ),
                Message("assistant", f"Request req-{index} completed normally."),
            )
        )
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
        code_detection=False,
    ),
)


async def _run(case: Case, history: list[Message]) -> SummarizationEvent:
    parsing = ParsingOptions(code_detector=None) if not case.code_detection else None
    async with ContextSummarizer(
        ScriptedModel(),
        trigger=("messages", 4),
        keep=("messages", 2),
        parsing=parsing,
    ) as summarizer:
        result = await summarizer.summarize(history)
    if result is None:
        raise RuntimeError(f"{case.name} history did not trigger summarization")
    return result.event


async def measure(case: Case, size: int, repeat: int) -> tuple[float, SummarizationEvent]:
    """Median milliseconds over ``repeat`` runs, with one warm-up run."""
    history = case.build(size)
    await _run(case, history)
    timings: list[float] = []
    event: SummarizationEvent | None = None
    for _ in range(repeat):
        gc.collect()
        gc.disable()
        try:
            start = time.perf_counter()
            event = await _run(case, history)
            timings.append(time.perf_counter() - start)
        finally:
            gc.enable()
    if event is None:
        raise RuntimeError("benchmark has no timed result")
    return statistics.median(timings) * 1_000, event


async def run(repeat: int, smoke: bool) -> None:
    """Run every case and print a table of the results."""
    header = f"{'case':<30}{'size':>16}{'tokens in':>12}{'tokens out':>12}{'ms':>10}"
    print(header)
    print("-" * len(header))
    for case in CASES:
        sizes = (case.smoke_size,) if smoke else case.sizes
        for size in sizes:
            milliseconds, event = await measure(case, size, repeat)
            print(
                f"{case.name:<30}{f'{size:,} {case.unit}':>16}"
                f"{event.input_tokens:>12,}{event.output_tokens:>12,}"
                f"{milliseconds:>10,.1f}"
            )


def main() -> None:
    """Parse arguments and run the benchmark."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--smoke", action="store_true", help="run each case once at a small size")
    parser.add_argument("--repeat", type=int, default=5, help="timed runs per case (default 5)")
    arguments = parser.parse_args()
    asyncio.run(run(1 if arguments.smoke else arguments.repeat, arguments.smoke))


if __name__ == "__main__":
    main()
