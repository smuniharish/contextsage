"""Log-heavy tool output example.

Demonstrates preservation of first/last occurrence, root cause, and trace
id even when thousands of repetitive INFO log lines are compressed away.
Uses a real chat model (see examples/_llm.py); requires EXPLABS_API_KEY.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from _llm import build_demo_model
from contextsage import IntelligentSummarizationMiddleware


def build_log_dump(num_lines: int = 500) -> str:
    lines = [
        f"2024-06-01T00:{minute:02d}:00 INFO trace_id=abcd1234 request handled ok"
        for minute in range(num_lines)
    ]
    lines.insert(0, "2024-06-01T00:00:00 INFO trace_id=abcd1234 service started")
    lines.append(
        "2024-06-01T08:20:00 ERROR trace_id=abcd1234 root cause: "
        "downstream service unreachable after 3 retries"
    )
    return "\n".join(lines)


def main() -> None:
    middleware = IntelligentSummarizationMiddleware(
        model=build_demo_model(),
        trigger=("tokens", 300),
        keep=("messages", 1),
    )

    conversation = [
        HumanMessage(content="Why did the service go down overnight?"),
        AIMessage(
            content="",
            tool_calls=[{"id": "call-1", "name": "get_service_logs", "args": {}}],
        ),
        ToolMessage(content=build_log_dump(), tool_call_id="call-1"),
    ]

    result = middleware.before_model({"messages": conversation}, None)
    if result is None:
        print("No summarization was required.")
        return

    combined_text = "\n".join(str(getattr(m, "content", "")) for m in result["messages"])
    print("trace_id preserved:", "abcd1234" in combined_text)
    print("root cause preserved:", "downstream service unreachable" in combined_text)


if __name__ == "__main__":
    main()
