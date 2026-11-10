"""Compact a large, mixed tool result without losing what matters.

Run: python examples/large_tool_output.py

A single MCP-style tool result mixes prose, a JSON payload with repeated
records, a long routine log, a warning and an error. The history is too short
to summarize, so ContextSage only compacts: repeated log lines collapse into
one marker with the omitted line range, identical JSON records collapse into a
counted entry, and every distinct line, warning, error and identifier stays.
"""

from __future__ import annotations

import asyncio
import json

from _shared import ScriptedModel

from contextsage import ContextSummarizer, Message, ToolCall

HEARTBEATS = "".join(
    f"2026-10-04T08:{index // 60:02d}:{index % 60:02d}Z "
    f"INFO checkout-worker-{index % 4} heartbeat ok\n"
    for index in range(150)
)
RESULT = {
    "service": "checkout",
    "region": "eu-west-1",
    "orders": [{"sku": "A-1", "qty": 1, "state": "queued"}] * 25
    + [{"sku": "B-7", "qty": 2, "state": "failed", "order_id": "ORD-5521"}],
}
TOOL_OUTPUT = (
    "Diagnostics for incident INC-4410 (checkout latency).\n"
    + json.dumps(RESULT)
    + "\n"
    + HEARTBEATS
    + "2026-10-04T08:02:31Z WARN slow query on orders took 2300 ms\n"
    + "2026-10-04T08:02:32Z ERROR payment authorization failed for order ORD-5521\n"
)
HISTORY = [
    Message("user", "Why is checkout slow?"),
    Message("assistant", "", tool_calls=(ToolCall("call-1", "diagnostics", {}),)),
    Message("tool", TOOL_OUTPUT, tool_call_id="call-1"),
]


async def main() -> None:
    async with ContextSummarizer(
        ScriptedModel("unused"), trigger=("tokens", 1_000), keep=("messages", 20)
    ) as summarizer:
        result = await summarizer.summarize(HISTORY)
    if result is None:
        raise SystemExit("The tool result was not compacted.")
    compacted = result.messages[-1].content
    before, after = len(TOOL_OUTPUT.splitlines()), len(compacted.splitlines())

    print(f"{before} lines before, {after} after")
    print()
    print(compacted)
    event = result.event
    print(f"tokens: {event.input_tokens} -> {event.output_tokens}")
    print(f"compacted units: {event.compacted_units}")
    print(f"content kinds: {event.content_kinds}")


if __name__ == "__main__":
    asyncio.run(main())
