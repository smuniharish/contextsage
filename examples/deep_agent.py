"""Use ContextSage as the memory compactor for a deep agent.

Run: python examples/deep_agent.py

Requires CONTEXTSAGE_LLM_API_KEY (and optionally CONTEXTSAGE_LLM_BASE_URL and
CONTEXTSAGE_LLM_MODEL); see the repository's .env.example. The deep agent and
the summary middleware share a model here; production applications can use a
smaller, cheaper model for summaries.
"""

from __future__ import annotations

import asyncio

from _shared import EventCollector, chat_model
from deepagents import HarnessProfile, create_deep_agent, register_harness_profile
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from contextsage.integrations.langchain import IntelligentSummarizationMiddleware


@tool
def deployment_log(service: str) -> str:
    """Return the deployment log of a service."""
    steps = "".join(
        f"2026-10-04T12:{index // 60:02d}:{index % 60:02d}Z INFO {service} rollout step ok\n"
        for index in range(300)
    )
    return (
        f"Deployment DEP-7310 of {service}.\n{steps}"
        "2026-10-04T12:05:01Z ERROR health check failed: readiness probe timeout\n"
    )


async def main() -> None:
    register_harness_profile(
        "openai",
        HarnessProfile(excluded_middleware=frozenset({"SummarizationMiddleware"})),
    )
    async with chat_model() as model:
        sink = EventCollector()
        middleware = IntelligentSummarizationMiddleware(
            model, trigger=("tokens", 2_000), keep=("messages", 6), sink=sink
        )
        agent = create_deep_agent(
            model=model,
            tools=[deployment_log],
            system_prompt="You investigate failed deployments. Be concise.",
            middleware=[middleware],
        )
        try:
            result = await agent.ainvoke(
                {"messages": [HumanMessage("Why did the checkout deployment fail?")]}
            )
        finally:
            await middleware.aclose()

    print("Answer:", result["messages"][-1].text)
    for event in sink.events:
        print(f"summarization: {event.input_tokens} -> {event.output_tokens} tokens")


if __name__ == "__main__":
    asyncio.run(main())
