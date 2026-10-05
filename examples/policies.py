"""Compare the three preservation policies on the same tool result.

Run: python examples/policies.py

``maximum_preservation`` only minifies JSON. ``balanced`` (the default) also
collapses runs of identical items, which loses nothing. ``maximum_compression``
groups identical items anywhere in a list and samples long lists.
"""

import json

from langchain_core.messages import AnyMessage, HumanMessage, ToolMessage
from langgraph.runtime import Runtime

from _models import scripted_model
from contextsage import IntelligentSummarizationMiddleware

inventory = {
    "warehouse": "berlin-2",
    "pallets": (
        [{"sku": "A-1", "state": "ok"}] * 3
        + [{"sku": "B-2", "state": "ok"}]
        + [{"sku": "A-1", "state": "ok"}] * 3
        + [{"sku": f"C-{index}", "state": "ok"} for index in range(12)]
    ),
}
history: list[AnyMessage] = [
    HumanMessage("Summarize the warehouse inventory."),
    ToolMessage(json.dumps(inventory, indent=2), tool_call_id="call-1"),
]

for policy in ("maximum_preservation", "balanced", "maximum_compression"):
    middleware = IntelligentSummarizationMiddleware(
        model=scripted_model("unused"),
        trigger=("tokens", 200),
        keep=("messages", 20),
        policy=policy,
    )
    update = middleware.before_model({"messages": history}, Runtime())
    if update is None:
        raise SystemExit("The tool result was not compacted.")
    compacted = update["messages"][-1].text
    print(f"{policy} ({len(compacted)} characters):")
    print(f"  {compacted}")
    print()
