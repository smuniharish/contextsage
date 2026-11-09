"""The framework-neutral message model ContextSage summarizes.

Every agent framework has its own message classes. ContextSage works on
`Message`, and a `contextsage.FrameworkAdapter` converts in both directions,
so the same engine serves LangChain, Agno, CrewAI or an in-house loop.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Literal, get_args

__all__ = ["Fact", "Message", "Role", "SummaryLineage", "ToolCall"]

type Role = Literal["system", "user", "assistant", "tool"]
"""Who wrote a message: the system prompt, the user, the agent's model or a tool."""

_ROLES = frozenset(get_args(Role.__value__))


@dataclass(frozen=True, slots=True)
class ToolCall:
    """One tool invocation requested by an assistant message.

    Attributes:
        id: Identifier that the matching tool result refers to.
        name: Tool name.
        arguments: JSON-compatible tool arguments.
    """

    id: str
    name: str
    arguments: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Fact:
    """Information a rewritten history must still contain.

    Attributes:
        statement: The text restated verbatim if the fact goes missing.
        required: Strings that must all appear in a single message, as whole
            words and ignoring case, whitespace and apostrophe style, for the
            fact to count as preserved.
    """

    statement: str
    required: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SummaryLineage:
    """Identity and ancestry of a summary message.

    Lineage travels with the summary message, so it survives checkpoints and
    needs no state in the engine.

    Attributes:
        summary_id: The summary message ID.
        generation: 1 for a first summary, 2 for a summary of a summary, and
            so on.
        source_summary_ids: IDs of the earlier summaries this one replaced.
        facts: Facts that later summarizations must keep, after the messages
            they came from are gone.
    """

    summary_id: str
    generation: int = 1
    source_summary_ids: tuple[str, ...] = ()
    facts: tuple[Fact, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Return the lineage as a JSON-compatible dictionary.

        Framework adapters store this dictionary in the native message's
        metadata and read it back with `from_dict`.
        """
        return {
            "summary_id": self.summary_id,
            "generation": self.generation,
            "source_summary_ids": list(self.source_summary_ids),
            "facts": [
                {"statement": fact.statement, "required": list(fact.required)}
                for fact in self.facts
            ],
        }

    @classmethod
    def from_dict(cls, record: object, *, summary_id: str) -> SummaryLineage:
        """Read a lineage record written by `to_dict`, tolerating damage.

        A record edited by hand or truncated in a checkpoint never fails a
        run: malformed fields fall back to the values of a first summary and
        malformed facts are skipped.

        Args:
            record: The stored record, of any type.
            summary_id: The ID of the message the record belongs to, used when
                the record does not name one.

        Returns:
            The lineage.
        """
        data = record if isinstance(record, Mapping) else {}
        recorded_id = data.get("summary_id")
        generation = data.get("generation")
        sources = data.get("source_summary_ids")
        facts = data.get("facts")
        return cls(
            summary_id=recorded_id if isinstance(recorded_id, str) and recorded_id else summary_id,
            generation=generation
            if isinstance(generation, int) and not isinstance(generation, bool) and generation > 0
            else 1,
            source_summary_ids=tuple(item for item in sources if isinstance(item, str))
            if isinstance(sources, (list, tuple))
            else (),
            facts=tuple(fact for entry in facts if (fact := _recorded_fact(entry)) is not None)
            if isinstance(facts, (list, tuple))
            else (),
        )


def _recorded_fact(entry: object) -> Fact | None:
    if not isinstance(entry, Mapping):
        return None
    statement = entry.get("statement")
    required = entry.get("required")
    if (
        not isinstance(statement, str)
        or not isinstance(required, (list, tuple))
        or not required
        or not all(isinstance(item, str) and item.strip() for item in required)
    ):
        return None
    return Fact(statement, tuple(required))


@dataclass(frozen=True, slots=True)
class Message:
    """One message of an agent's history.

    Attributes:
        role: ``"system"``, ``"user"``, ``"assistant"`` or ``"tool"``.
        content: The message text. For multimodal content, the text parts.
        id: Stable message ID; provenance links refer to it.
        name: Optional author name, such as the agent of a multi-agent swarm.
        tool_calls: Tool invocations requested by an assistant message.
        tool_call_id: For a tool result, the ID of the call it answers.
        rewritable: Whether ContextSage may rewrite ``content``. Adapters set
            it to ``False`` for content that is not plain text, such as image
            blocks, so it is never compacted.
        lineage: Set on summary messages; see `SummaryLineage`.
        native: The framework's own message object, for adapters to update
            instead of rebuilding. Ignored by ContextSage and by equality.

    Raises:
        ValueError: If ``role`` is unknown or ``content`` is not a string.
    """

    role: Role
    content: str
    id: str | None = None
    name: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None
    rewritable: bool = True
    lineage: SummaryLineage | None = None
    native: object = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        if self.role not in _ROLES:
            raise ValueError(f"role must be one of {sorted(_ROLES)}, got {self.role!r}")
        if not isinstance(self.content, str):
            raise ValueError("content must be a string")

    @property
    def is_summary(self) -> bool:
        """Whether the message is a summary of earlier history."""
        return self.lineage is not None

    def with_content(self, content: str) -> Message:
        """Return a copy with new ``content``, keeping every other field."""
        return replace(self, content=content)
