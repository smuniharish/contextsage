"""Keep corrections, instructions and conflicting evidence through summarization.

Run: python examples/preservation.py

The summary model below writes a vague summary that drops everything that
matters. ContextSage notices that the user's correction, a standing
instruction, an identifier tied to a failure and two conflicting sources are
missing, and restates them verbatim inside the summary message.
"""

from __future__ import annotations

import asyncio

from _shared import ScriptedModel

from contextsage import ContextSummarizer, Message, ToolCall

HISTORY = [
    Message("user", "You must never refund more than 500 dollars without approval."),
    Message("user", "Please refund order ORD-1001 for customer 123."),
    Message("assistant", "", tool_calls=(ToolCall("c1", "warehouse_status", {}),)),
    Message("tool", "warehouse: status=SHIPPED", tool_call_id="c1"),
    Message("assistant", "", tool_calls=(ToolCall("c2", "carrier_status", {}),)),
    Message("tool", "carrier: status=LOST, refund claim TX-7781 failed", tool_call_id="c2"),
    Message("user", "No, use customer 456 instead of customer 123."),
    Message("assistant", "Understood."),
    Message("user", "What should we do next?"),
]


async def main() -> None:
    async with ContextSummarizer(
        ScriptedModel("The user asked about refunds and an order."),
        trigger=("messages", 8),
        keep=("messages", 2),
    ) as summarizer:
        result = await summarizer.summarize(HISTORY)
    if result is None:
        raise SystemExit("The history did not trigger summarization.")
    summary = next(message for message in result.messages if message.is_summary)

    print(summary.content)
    print()
    event = result.event
    print(f"validation: {event.validation_status}, recovery: {event.recovery_status}")


if __name__ == "__main__":
    asyncio.run(main())
