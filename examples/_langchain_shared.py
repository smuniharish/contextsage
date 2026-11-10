"""LangChain-only scripted model helpers for the integration examples."""

from __future__ import annotations

from itertools import chain, repeat
from typing import TYPE_CHECKING, Any, override

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

if TYPE_CHECKING:
    from collections.abc import Sequence

    from langchain_core.language_models import BaseChatModel
    from langchain_core.runnables import Runnable


class ScriptedChatModel(GenericFakeChatModel):
    """A LangChain chat model that answers from a script and accepts any tools."""

    @override
    def bind_tools(self, tools: Sequence[object], **kwargs: Any) -> Runnable[Any, AIMessage]:
        return self


def scripted_chat_model(*replies: str | AIMessage) -> BaseChatModel:
    """A LangChain chat model that answers with ``replies`` in turn, repeating the last."""
    messages = [reply if isinstance(reply, AIMessage) else AIMessage(reply) for reply in replies]
    return ScriptedChatModel(messages=chain(messages, repeat(messages[-1])))
