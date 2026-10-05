"""Replace a deep agent's built-in summarization with ContextSage.

Run: python examples/deep_agent.py

Requires CONTEXTSAGE_LLM_API_KEY (and optionally CONTEXTSAGE_LLM_BASE_URL and
CONTEXTSAGE_LLM_MODEL); see .env.example. ``deepagents`` adds LangChain's
``SummarizationMiddleware`` to every deep agent. A harness profile removes it
so that ContextSage replaces it rather than running alongside it.
"""

from deepagents import HarnessProfile, create_deep_agent, register_harness_profile
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from _models import live_model
from contextsage import IntelligentSummarizationMiddleware, SummarizationEvent


@tool
def deployment_log(service: str) -> str:
    """Return the deployment log of a service."""
    steps = "".join(
        f"2026-10-04T12:{index // 60:02d}:{index % 60:02d}Z INFO {service} rollout "
        "step ok\n"
        for index in range(300)
    )
    return (
        f"Deployment DEP-7310 of {service}.\n{steps}"
        "2026-10-04T12:05:01Z ERROR health check failed: readiness probe timeout\n"
    )


register_harness_profile(
    "openai",
    HarnessProfile(excluded_middleware=frozenset({"SummarizationMiddleware"})),
)

model = live_model()
events: list[SummarizationEvent] = []
agent = create_deep_agent(
    model=model,
    tools=[deployment_log],
    system_prompt="You investigate failed deployments. Be concise.",
    middleware=[
        IntelligentSummarizationMiddleware(
            model=model,
            trigger=("tokens", 2_000),
            keep=("messages", 6),
            observability_hook=events.append,
        )
    ],
)
result = agent.invoke(
    {"messages": [HumanMessage("Why did the checkout deployment fail?")]}
)

print("Answer:", result["messages"][-1].text)
for event in events:
    print(f"summarization: {event.input_tokens} -> {event.output_tokens} tokens")
