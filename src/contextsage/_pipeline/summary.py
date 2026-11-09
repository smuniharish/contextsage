"""The summary-model request: prompt, transcript and size limit."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from xml.sax.saxutils import escape, quoteattr

from contextsage.messages import Message

if TYPE_CHECKING:
    from collections.abc import Sequence

    from contextsage.contracts import TokenCounter

DEFAULT_SUMMARY_PROMPT = """\
You maintain the working memory of an AI agent. The conversation below is \
about to be removed from the agent's context, and your summary will replace \
it. The agent must be able to continue the task from your summary alone.

Write a concise summary in plain prose and short lists that records:
- the user's goal and every requirement, constraint or preference they stated;
- decisions made and the reasons for them, including corrections of earlier \
statements (state only the corrected value);
- work completed, with the results that later steps depend on;
- open questions, errors that are still unresolved, and the next steps.

Copy identifiers, numbers, file paths, URLs, commands, error messages and \
names exactly as they appear. Do not invent details, do not address the \
user, and do not continue the conversation. Reply with the summary only.

<conversation>
{messages}
</conversation>"""
"""The default prompt; it must contain a ``{messages}`` placeholder."""

SUMMARY_PREFIX = "Summary of the conversation so far:\n\n"
TRIM_MARKER = "\n[... earlier messages trimmed to fit the summary budget ...]\n"


def transcript(messages: Sequence[Message]) -> str:
    """Render messages as an XML transcript the summary model can read."""
    lines: list[str] = []
    for message in messages:
        attributes = [f"role={quoteattr(message.role)}"]
        if message.name:
            attributes.append(f"name={quoteattr(message.name)}")
        if message.tool_call_id:
            attributes.append(f"tool_call_id={quoteattr(message.tool_call_id)}")
        if message.is_summary:
            attributes.append('summary="true"')
        body = escape(message.content)
        calls = "".join(
            f"\n<tool_call id={quoteattr(call.id)} name={quoteattr(call.name)}>"
            f"{escape(_arguments(call.arguments))}</tool_call>"
            for call in message.tool_calls
        )
        lines.append(f"<message {' '.join(attributes)}>{body}{calls}</message>")
    return "\n".join(lines)


def _arguments(arguments: object) -> str:
    return json.dumps(arguments, ensure_ascii=False, sort_keys=True, default=str)


async def fit(text: str, limit: int | None, counter: TokenCounter) -> str:
    """Shorten ``text`` to about ``limit`` tokens by removing its middle.

    A quarter of the kept text comes from the start, which states the task,
    and three quarters from the end, which holds the latest state.
    """
    if limit is None:
        return text
    tokens = await counter.count([Message("user", text)])
    if tokens <= limit:
        return text
    keep = len(text) * limit // tokens
    head = keep // 4
    tail = keep - head
    return f"{text[:head]}{TRIM_MARKER}{text[len(text) - tail :]}"


def summary_text(reply: str) -> str:
    """Return the content of the summary message for a model reply."""
    return f"{SUMMARY_PREFIX}{reply.strip()}"
