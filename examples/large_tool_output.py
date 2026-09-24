"""Large tool output example: a single huge MCP-style result mixing
explanatory text, JSON, and 100+ repeated log lines.

Demonstrates that ContextIQ deterministically compresses the log-heavy
portion while protecting the transaction id and root cause, instead of
forcing the whole 100K-token result into one semantic LLM summarization
call. Uses a real chat model (see examples/_llm.py); requires EXPLABS_API_KEY.
"""

from __future__ import annotations

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from _llm import build_demo_model
from contextiq import IntelligentSummarizationMiddleware


def build_large_tool_result() -> str:
    explanatory_text = (
        "The nightly batch job for the billing pipeline failed partway through "
        "processing. Below is the raw execution log and the final status payload."
    )
    log_lines = "\n".join(
        f"2024-03-01T02:00:{i:02d} INFO worker-{i % 4} processed batch item {i}" for i in range(200)
    )
    status_payload = json.dumps(
        {
            "status": "failed",
            "transaction_id": "TX-77123",
            "batch_id": "BATCH-2024-03-01",
            "errors": ["connection pool exhausted", "retry limit exceeded"],
        }
    )
    final_error_line = "2024-03-01T02:03:41 ERROR root cause: PostgreSQL connection pool exhaustion"
    return f"{explanatory_text}\n{status_payload}\n{log_lines}\n{final_error_line}"


def main() -> None:
    middleware = IntelligentSummarizationMiddleware(
        model=build_demo_model(),
        trigger=("tokens", 500),
        keep=("messages", 2),
    )

    conversation = [
        HumanMessage(content="Please check on last night's billing batch job."),
        AIMessage(
            content="",
            tool_calls=[{"id": "call-1", "name": "get_batch_status", "args": {}}],
        ),
        ToolMessage(content=build_large_tool_result(), tool_call_id="call-1"),
        AIMessage(content="Let me look into the failure details for you."),
    ]

    result = middleware.before_model({"messages": conversation}, None)
    if result is None:
        print("No summarization was required.")
        return

    combined_text = "\n".join(str(getattr(m, "content", "")) for m in result["messages"])
    print("Summarization triggered.")
    print("TX-77123 preserved:", "TX-77123" in combined_text)
    print("Root cause preserved:", "PostgreSQL connection pool exhaustion" in combined_text)
    for message in result["messages"]:
        print(f"  [{type(message).__name__}] {str(getattr(message, 'content', ''))[:150]}")


if __name__ == "__main__":
    main()
