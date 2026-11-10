"""Summarize a long agent history with ContextSage, in plain Python.

Run: python examples/quickstart.py

ContextSage works on `contextsage.Message` objects, so it fits any agent
framework. The history below has a large tool result that pushes it past the
trigger. ContextSage compacts the repetitive log and JSON in that result, the
summary model summarizes the older messages, and ContextSage checks that the
incident and transaction IDs survived.
"""

from __future__ import annotations

import asyncio
import json

from _shared import ScriptedModel, show_history

from contextsage import ContextSummarizer, Message, ToolCall

LOG = "".join(
    f"2026-10-04T03:{index // 60:02d}:{index % 60:02d}Z INFO payments-worker processing queue\n"
    for index in range(200)
)
REPORT = (
    "Incident INC-9931: elevated latency on the payments service.\n"
    + json.dumps({"orders": [{"status": "queued"}] * 40, "region": "eu-west-1"})
    + "\n"
    + LOG
    + "2026-10-04T04:00:00Z ERROR connection pool exhausted for TX-991\n"
)
HISTORY = [
    Message("system", "You are an on-call SRE assistant.", id="s"),
    Message("user", "Investigate the payments outage.", id="u1"),
    Message("assistant", "", id="a1", tool_calls=(ToolCall("call-1", "incident_report", {}),)),
    Message("tool", REPORT, id="t1", tool_call_id="call-1"),
    Message("assistant", "INC-9931 is caused by connection pool exhaustion.", id="a2"),
    Message("user", "Is any other service affected?", id="u2"),
]


async def main() -> None:
    model = ScriptedModel(
        "The payments outage INC-9931 was traced to transaction TX-991 and a "
        "saturated connection pool."
    )
    async with ContextSummarizer(
        model, trigger=("tokens", 2_000), keep=("messages", 2)
    ) as summarizer:
        result = await summarizer.summarize(HISTORY, thread_id="incident-9931")
    if result is None:
        raise SystemExit("The history did not trigger summarization.")

    print("History after summarization:")
    show_history(result.messages)
    event = result.event
    print()
    print(f"tokens before:      {event.input_tokens}")
    print(f"after compaction:   {event.prepared_tokens}")
    print(f"after summary:      {event.output_tokens}")
    print(f"compression ratio:  {event.compression_ratio:.3f}")
    print(f"validation:         {event.validation_status}")
    print(f"must-keep facts:    {event.must_preserve_facts}")


if __name__ == "__main__":
    asyncio.run(main())
