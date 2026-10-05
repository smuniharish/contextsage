"""Keep the agent running when the summary model fails.

Run: python examples/recovery.py

The summary model is unavailable. Instead of failing the agent turn,
ContextSage trims the history to the ``keep`` window with LangChain's
``trim_messages``, never orphaning a tool result, and restates the facts that
the trimmed messages carried.
"""

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatResult
from langgraph.runtime import Runtime

from _models import first_line
from contextsage import IntelligentSummarizationMiddleware, SummarizationEvent


class UnavailableModel(BaseChatModel):
    """A chat model whose provider is down."""

    @property
    def _llm_type(self) -> str:
        return "unavailable"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: object,
    ) -> ChatResult:
        raise TimeoutError("the summary model did not respond")


events: list[SummarizationEvent] = []
middleware = IntelligentSummarizationMiddleware(
    model=UnavailableModel(),
    trigger=("messages", 6),
    keep=("messages", 2),
    observability_hook=events.append,
)

history: list[AnyMessage] = [
    HumanMessage("Check order ORD-2207 for customer 812."),
    AIMessage("", tool_calls=[{"id": "c1", "name": "order_status", "args": {}}]),
    ToolMessage(
        "order ORD-2207: payment failed, gateway error GW-5003", tool_call_id="c1"
    ),
    AIMessage("Payment for ORD-2207 failed with GW-5003."),
    HumanMessage("Retry the payment."),
    AIMessage("", tool_calls=[{"id": "c2", "name": "retry_payment", "args": {}}]),
    ToolMessage("retry accepted", tool_call_id="c2"),
]

update = middleware.before_model({"messages": history}, Runtime())
if update is None:
    raise SystemExit("The history did not trigger summarization.")

# The update replaces the history: a RemoveMessage, then the new messages.
print("History after the fallback:")
for message in update["messages"][1:]:
    calls = ", ".join(call["name"] for call in getattr(message, "tool_calls", []))
    print(f"  {message.type:<5} {first_line(message.text, 100) or f'calls {calls}'}")
    for line in message.text.splitlines()[1:]:
        print(f"        {line}")
event = events[0]
print()
print(f"validation: {event.validation_status}, recovery: {event.recovery_status}")
