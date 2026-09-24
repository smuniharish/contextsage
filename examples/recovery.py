"""Recovery example.

Demonstrates ContextSage's fail-safe behavior when the underlying LLM call
fails entirely: it falls back to a deterministic trim while explicitly
restating any must-preserve facts, rather than corrupting the conversation
or silently losing critical information.

This example intentionally uses a model that always raises (rather than
the real chat model in examples/_llm.py) because it specifically exercises
the failure-recovery path, which requires a guaranteed provider outage.
"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage

from contextsage import IntelligentSummarizationMiddleware


class AlwaysFailingModel(BaseChatModel):
    """Simulates a provider outage: every generation attempt raises."""

    @property
    def _llm_type(self) -> str:
        return "always-failing-demo-model"

    def _generate(self, *args, **kwargs):
        raise RuntimeError("simulated provider outage")

    async def _agenerate(self, *args, **kwargs):
        raise RuntimeError("simulated provider outage")


def main() -> None:
    middleware = IntelligentSummarizationMiddleware(
        model=AlwaysFailingModel(),
        trigger=("tokens", 20),
        keep=("messages", 2),
    )

    conversation = [
        HumanMessage(content="Use staging database, not production.", id="h1"),
        AIMessage(content="Understood, using staging.", id="a1"),
    ] * 10

    result = middleware.before_model({"messages": conversation}, None)
    assert result is not None, "summarization should still trigger and recover"
    combined_text = "\n".join(str(getattr(m, "content", "")) for m in result["messages"])
    print("Recovered gracefully despite LLM failure.")
    print("Constraint preserved:", "staging" in combined_text.lower())


if __name__ == "__main__":
    main()
