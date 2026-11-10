"""Keep the agent running when the summary model fails.

Run: python examples/recovery.py

The summary model is unavailable. Instead of failing the agent turn,
ContextSage trims the history to the ``keep`` window, never orphaning a tool
result, and restates the facts that the trimmed messages carried.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, override

from _shared import first_line
from parsefabric import LanguageModel

from contextsage import ContextSummarizer, Message, ToolCall

if TYPE_CHECKING:
    from collections.abc import Sequence

    from parsefabric import ChatMessage


class UnavailableModel(LanguageModel):
    """A summary model whose provider is down."""

    @override
    async def complete(self, messages: Sequence[ChatMessage]) -> str:
        raise TimeoutError("the summary model did not respond")


HISTORY = [
    Message("user", "Check order ORD-2207 for customer 812."),
    Message("assistant", "", tool_calls=(ToolCall("c1", "order_status", {}),)),
    Message("tool", "order ORD-2207: payment failed, gateway error GW-5003", tool_call_id="c1"),
    Message("assistant", "Payment for ORD-2207 failed with GW-5003."),
    Message("user", "Retry the payment."),
    Message("assistant", "", tool_calls=(ToolCall("c2", "retry_payment", {}),)),
    Message("tool", "retry accepted", tool_call_id="c2"),
]


async def main() -> None:
    async with ContextSummarizer(
        UnavailableModel(), trigger=("messages", 6), keep=("messages", 2)
    ) as summarizer:
        result = await summarizer.summarize(HISTORY)
    if result is None:
        raise SystemExit("The history did not trigger summarization.")

    print("History after the fallback:")
    for message in result.messages:
        calls = ", ".join(call.name for call in message.tool_calls)
        print(f"  {message.role:<9} {first_line(message.content, 100) or f'calls {calls}'}")
        for line in message.content.splitlines()[1:]:
            print(f"            {line}" if line else "")
    event = result.event
    print()
    print(f"validation: {event.validation_status}, recovery: {event.recovery_status}")


if __name__ == "__main__":
    asyncio.run(main())
