"""Keep corrections, instructions and conflicting evidence through summarization.

Run: python examples/preservation.py

The summary model below writes a vague summary that drops everything that
matters. ContextSage notices that the user's correction, a standing
instruction, an identifier tied to a failure and two conflicting sources are
missing, and restates them verbatim inside the summary message.
"""

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langgraph.runtime import Runtime

from _models import scripted_model
from contextsage import IntelligentSummarizationMiddleware, SummarizationEvent

events: list[SummarizationEvent] = []
middleware = IntelligentSummarizationMiddleware(
    model=scripted_model("The user asked about refunds and an order."),
    trigger=("messages", 8),
    keep=("messages", 2),
    observability_hook=events.append,
)

history: list[AnyMessage] = [
    HumanMessage("You must never refund more than 500 dollars without approval."),
    HumanMessage("Please refund order ORD-1001 for customer 123."),
    AIMessage("", tool_calls=[{"id": "c1", "name": "warehouse_status", "args": {}}]),
    ToolMessage("warehouse: status=SHIPPED", tool_call_id="c1"),
    AIMessage("", tool_calls=[{"id": "c2", "name": "carrier_status", "args": {}}]),
    ToolMessage("carrier: status=LOST, refund claim TX-7781 failed", tool_call_id="c2"),
    HumanMessage("No, use customer 456 instead of customer 123."),
    AIMessage("Understood."),
    HumanMessage("What should we do next?"),
]

update = middleware.before_model({"messages": history}, Runtime())
if update is None:
    raise SystemExit("The history did not trigger summarization.")
# The update replaces the history: a RemoveMessage, then the new messages.
summary = update["messages"][1]

print(summary.text)
print()
event = events[0]
print(f"validation: {event.validation_status}, recovery: {event.recovery_status}")
