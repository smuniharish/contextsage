"""Mixed MCP output example: one ToolMessage containing prose, JSON, logs,
and a code snippet all at once.

Demonstrates that ContextIQ never treats the whole message as one content
type: each region is decomposed and classified independently. Uses a real
chat model (see examples/_llm.py); requires EXPLABS_API_KEY.
"""

from __future__ import annotations

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from _llm import build_demo_model
from contextiq import IntelligentSummarizationMiddleware


def build_mixed_mcp_result() -> str:
    return "\n".join(
        [
            "The deployment tool ran a health check and applied a hotfix.",
            json.dumps({"deployment_id": "DEP-4471", "status": "degraded", "region": "us-east-1"}),
            "2024-05-01T00:00:01 INFO health check started",
            "2024-05-01T00:00:02 INFO health check started",
            "2024-05-01T00:00:03 WARN latency above threshold",
            "```python",
            "def rollback(deployment_id: str) -> None:",
            "    trigger_rollback(deployment_id)",
            "```",
            "Recommendation: roll back DEP-4471 if latency does not recover in 5 minutes.",
        ]
    )


def main() -> None:
    middleware = IntelligentSummarizationMiddleware(
        model=build_demo_model(),
        trigger=("tokens", 100),
        keep=("messages", 1),
    )

    conversation = [
        HumanMessage(content="What's the status of our latest deployment?"),
        AIMessage(
            content="",
            tool_calls=[{"id": "call-1", "name": "get_deployment_status", "args": {}}],
        ),
        ToolMessage(content=build_mixed_mcp_result(), tool_call_id="call-1"),
    ]

    result = middleware.before_model({"messages": conversation}, None)
    if result is None:
        print("No summarization was required.")
        return

    combined_text = "\n".join(str(getattr(m, "content", "")) for m in result["messages"])
    print("DEP-4471 preserved:", "DEP-4471" in combined_text)
    for message in result["messages"]:
        print(f"  [{type(message).__name__}] {str(getattr(message, 'content', ''))[:150]}")


if __name__ == "__main__":
    main()
