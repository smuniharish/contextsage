"""Basic ContextSage usage: the "extremely simple" primary experience.

Run with:

    python examples/basic.py

Requires a real API key: copy .env.example to .env and set EXPLABS_API_KEY.
This example calls a live LLM (see examples/_llm.py) so the summary text
below reflects an actual model response, not a scripted fake.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from _llm import build_demo_model
from contextsage import IntelligentSummarizationMiddleware


def main() -> None:
    middleware = IntelligentSummarizationMiddleware(
        model=build_demo_model(),
        trigger=("tokens", 40),
        keep=("messages", 4),
    )

    conversation = [
        HumanMessage(content="I'm planning a trip to Kyoto in April."),
        AIMessage(content="Great choice! What are you most interested in seeing?"),
        HumanMessage(content="Temples and good food, mostly. I'll have 4 days."),
        AIMessage(content="Understood — temples and food, 4 days. Let me draft an itinerary."),
        HumanMessage(content="Also I'd prefer to avoid very touristy restaurants."),
        AIMessage(content="Noted, I'll prioritize local spots over tourist traps."),
        HumanMessage(content="What's the weather usually like in April?"),
        AIMessage(content="April in Kyoto is mild, with cherry blossoms typically in bloom."),
    ]

    result = middleware.before_model({"messages": conversation}, None)
    if result is None:
        print("No summarization was required.")
        return

    print("Summarization triggered. Resulting message list:")
    for message in result["messages"]:
        kind = type(message).__name__
        content = str(getattr(message, "content", ""))[:120]
        print(f"  [{kind}] {content}")


if __name__ == "__main__":
    main()
