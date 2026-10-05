"""Observe every summarization through logging and a hook.

Run: python examples/observability.py

Each summarization emits one content-free ``SummarizationEvent``. It is logged
to the ``contextsage`` logger at INFO level, with the event under the
``contextsage`` key of the log record, and passed to ``observability_hook``.
Neither ever contains message content.
"""

import json
import logging

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langgraph.runtime import Runtime

from _models import scripted_model
from contextsage import IntelligentSummarizationMiddleware, SummarizationEvent

VOLATILE = {"summary_id", "latency_ms"}


class JSONEventHandler(logging.Handler):
    """Print the structured event attached to ContextSage log records."""

    def emit(self, record: logging.LogRecord) -> None:
        event = {
            key: value
            for key, value in getattr(record, "contextsage", {}).items()
            if key not in VOLATILE
        }
        print(f"log record '{record.getMessage()}':")
        print(json.dumps(event, indent=2))


logger = logging.getLogger("contextsage")
logger.setLevel(logging.INFO)
logger.addHandler(JSONEventHandler())


def alert_on_lost_facts(event: SummarizationEvent) -> None:
    """A hook: flag summaries that needed facts restated."""
    if event.recovery_status != "none_needed":
        print(f"hook: recovery '{event.recovery_status}' after {event.trigger_reason}")


middleware = IntelligentSummarizationMiddleware(
    model=scripted_model("Discussed the invoice."),
    trigger=("messages", 6),
    keep=("messages", 2),
    observability_hook=alert_on_lost_facts,
)
billing_log = "".join(
    f"2026-10-04T07:{index // 60:02d}:{index % 60:02d}Z INFO billing-worker charge ok\n"
    for index in range(120)
)
history: list[AnyMessage] = [
    HumanMessage("Invoice INV-2048 for customer 77 was charged twice."),
    AIMessage("", tool_calls=[{"id": "c1", "name": "billing_log", "args": {}}]),
    ToolMessage(
        billing_log + "2026-10-04T09:00:00Z ERROR duplicate charge for INV-2048\n",
        tool_call_id="c1",
    ),
    AIMessage("The billing log shows a duplicate charge for INV-2048."),
    HumanMessage("Refund the duplicate."),
    AIMessage("Refund issued."),
]
middleware.before_model({"messages": history}, Runtime())
