"""Compact a large, mixed tool result without losing what matters.

Run: python examples/large_tool_output.py

A single MCP-style tool result mixes prose, a JSON payload with repeated
records, a long routine log, warnings and an error. The history is too short
to summarize, so ContextSage only compacts: repeated log lines collapse into
one marker with the omitted line range, identical JSON records collapse into a
counted entry, and every distinct line, warning, error and identifier stays.
"""

import json

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langgraph.runtime import Runtime

from _models import scripted_model
from contextsage import IntelligentSummarizationMiddleware, SummarizationEvent

events: list[SummarizationEvent] = []
middleware = IntelligentSummarizationMiddleware(
    model=scripted_model("unused"),
    trigger=("tokens", 1_000),
    keep=("messages", 20),
    observability_hook=events.append,
)

heartbeats = "".join(
    f"2026-10-04T08:{index // 60:02d}:{index % 60:02d}Z "
    f"INFO checkout-worker-{index % 4} heartbeat ok\n"
    for index in range(150)
)
result = {
    "service": "checkout",
    "region": "eu-west-1",
    "orders": [{"sku": "A-1", "qty": 1, "state": "queued"}] * 25
    + [{"sku": "B-7", "qty": 2, "state": "failed", "order_id": "ORD-5521"}],
}
tool_output = (
    "Diagnostics for incident INC-4410 (checkout latency).\n"
    + json.dumps(result)
    + "\n"
    + heartbeats
    + "2026-10-04T08:02:31Z WARN slow query on orders took 2300 ms\n"
    + "2026-10-04T08:02:32Z ERROR payment authorization failed for order ORD-5521\n"
)
history: list[AnyMessage] = [
    HumanMessage("Why is checkout slow?"),
    AIMessage("", tool_calls=[{"id": "call-1", "name": "diagnostics", "args": {}}]),
    ToolMessage(tool_output, tool_call_id="call-1"),
]

update = middleware.before_model({"messages": history}, Runtime())
if update is None:
    raise SystemExit("The tool result was not compacted.")
compacted = update["messages"][-1].text
before, after = len(tool_output.splitlines()), len(compacted.splitlines())

print(f"{before} lines before, {after} after")
print()
print(compacted)
event = events[0]
print(f"tokens: {event.input_tokens} -> {event.output_tokens}")
print(f"compacted units: {event.compacted_units}")
print(f"content kinds: {event.content_kinds}")
