"""RAG / search results example.

Demonstrates that ContextSage preserves source identity and does not
collapse contradictory retrieved evidence into a single false certainty.
Uses a real chat model (see examples/_llm.py); requires EXPLABS_API_KEY.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, ToolMessage

from _llm import build_demo_model
from contextsage import IntelligentSummarizationMiddleware


def main() -> None:
    middleware = IntelligentSummarizationMiddleware(
        model=build_demo_model(),
        trigger=("tokens", 50),
        keep=("messages", 1),
    )

    conversation = [
        HumanMessage(content="Has feature X shipped yet?"),
        ToolMessage(
            content=(
                "Source: docs.example.com/feature-x\nstatus=SUCCESS\nFeature X shipped in v2.3."
            ),
            tool_call_id="call-1",
        ),
        ToolMessage(
            content=(
                "Source: changelog.example.com\nstatus=FAILED\n"
                "Feature X is not yet released; still pending QA."
            ),
            tool_call_id="call-2",
        ),
    ]

    result = middleware.before_model({"messages": conversation}, None)
    if result is None:
        print("No summarization was required.")
        return

    combined_text = "\n".join(str(getattr(m, "content", "")) for m in result["messages"])
    print(
        "Both conflicting values survived:",
        "success" in combined_text.lower() and "failed" in combined_text.lower(),
    )


if __name__ == "__main__":
    main()
