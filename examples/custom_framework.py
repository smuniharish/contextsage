"""Use ContextSage with any agent framework through a `FrameworkAdapter`.

Run: python examples/custom_framework.py

ContextSage itself is framework-agnostic. A `FrameworkAdapter` converts a
framework's messages to `contextsage.Message` and back, so the same engine
serves Agno, CrewAI, the OpenAI Agents SDK, or a hand-written loop. This
adapter handles OpenAI-style chat dictionaries, the format most frameworks
pass to their model clients. The summary model is any parsefabric
`LanguageModel`; wrap your framework's client the same way.

The loop below calls `ContextSummarizer.summarize` before each model call, as
an integration would, and keeps summary lineage on the message dictionaries
so a later summary records that it replaced an earlier one.
"""

from __future__ import annotations

import asyncio
from typing import Any, cast, override

from _shared import ScriptedModel

from contextsage import ContextSummarizer, FrameworkAdapter, Message, Role, SummaryLineage, ToolCall

type ChatDict = dict[str, Any]
LINEAGE = "contextsage_lineage"


class ChatDictAdapter(FrameworkAdapter[ChatDict]):
    """Converts OpenAI-style chat dictionaries."""

    @override
    def to_message(self, native: ChatDict) -> Message:
        lineage = native.get(LINEAGE)
        return Message(
            cast("Role", native["role"]),
            native.get("content") or "",
            id=native.get("id"),
            tool_calls=tuple(
                ToolCall(call["id"], call["function"]["name"], call["function"]["arguments"])
                for call in native.get("tool_calls", ())
            ),
            tool_call_id=native.get("tool_call_id"),
            lineage=None
            if lineage is None
            else SummaryLineage.from_dict(lineage, summary_id=native["id"]),
            native=native,
        )

    @override
    def from_message(self, message: Message) -> ChatDict:
        if isinstance(message.native, dict) and message.native.get("content") == message.content:
            return cast("ChatDict", message.native)
        native: ChatDict = {"role": message.role, "content": message.content, "id": message.id}
        if message.tool_calls:
            native["tool_calls"] = [
                {"id": call.id, "function": {"name": call.name, "arguments": dict(call.arguments)}}
                for call in message.tool_calls
            ]
        if message.tool_call_id is not None:
            native["tool_call_id"] = message.tool_call_id
        if message.lineage is not None:
            native[LINEAGE] = message.lineage.to_dict()
        return native


def tool_turn(index: int) -> list[ChatDict]:
    """A user question, the tool call it caused, a large tool result and an answer."""
    log = "".join(
        f"2026-10-04T05:{minute:02d}:00Z INFO replica-{index} sync ok\n" for minute in range(60)
    )
    call = {
        "id": f"call-{index}",
        "function": {"name": "replica_log", "arguments": {"replica": index}},
    }
    return [
        {
            "role": "user",
            "content": f"Check replica {index} for ticket TCK-{700 + index}.",
            "id": f"u{index}",
        },
        {"role": "assistant", "content": "", "id": f"a{index}", "tool_calls": [call]},
        {"role": "tool", "content": log, "id": f"t{index}", "tool_call_id": f"call-{index}"},
        {"role": "assistant", "content": f"Replica {index} is healthy.", "id": f"r{index}"},
    ]


async def main() -> None:
    adapter = ChatDictAdapter()
    history: list[ChatDict] = [
        {"role": "system", "content": "You are a database assistant.", "id": "s"}
    ]
    async with ContextSummarizer(
        ScriptedModel("The user had replicas checked; all were healthy."),
        trigger=("messages", 9),
        keep=("messages", 4),
        propagate_errors=adapter.propagated_errors,
    ) as summarizer:
        for index in range(1, 5):
            history += tool_turn(index)
            result = await summarizer.summarize(adapter.to_messages(history), thread_id="replicas")
            if result is not None:
                history = adapter.from_messages(result.messages)
                event = result.event
                print(
                    f"turn {index}: summarized {event.input_messages} -> {event.output_messages} "
                    f"messages, generation {event.generation}"
                )

    print()
    print("Final history:")
    for message in history:
        generation = message.get(LINEAGE, {}).get("generation")
        label = f"summary (generation {generation})" if generation else message["role"]
        text = message["content"].partition("\n\n")[2] if generation else message["content"]
        print(f"  {label:<24} {(text or 'tool call').splitlines()[0][:60]}")


if __name__ == "__main__":
    asyncio.run(main())
