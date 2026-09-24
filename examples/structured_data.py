"""Structured data (JSON) example.

Demonstrates deterministic JSON deduplication/compaction as a targeted
transformation, distinct from LLM-based semantic summarization. Uses a
real chat model (see examples/_llm.py); requires EXPLABS_API_KEY.
"""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, ToolMessage

from _llm import build_demo_model
from contextsage import IntelligentSummarizationMiddleware


def build_repetitive_json_payload() -> str:
    records = [{"user_id": i % 5, "action": "ping", "status": "ok"} for i in range(200)]
    records.append(
        {"user_id": 42, "action": "checkout", "status": "failed", "order_id": "ORD-9981"}
    )
    return json.dumps({"transaction_id": "TX-500", "records": records})


def main() -> None:
    middleware = IntelligentSummarizationMiddleware(
        model=build_demo_model(),
        trigger=("tokens", 200),
        keep=("messages", 1),
    )

    conversation = [
        HumanMessage(content="Any failed checkouts recently?"),
        ToolMessage(content=build_repetitive_json_payload(), tool_call_id="call-1"),
    ]

    result = middleware.before_model({"messages": conversation}, None)
    if result is None:
        print("No summarization was required.")
        return

    combined_text = "\n".join(str(getattr(m, "content", "")) for m in result["messages"])
    print("ORD-9981 preserved:", "ORD-9981" in combined_text)
    print("TX-500 preserved:", "TX-500" in combined_text)


if __name__ == "__main__":
    main()
