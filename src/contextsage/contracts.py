"""Extension points of ContextSage, as abstract base classes.

Subclass one of these to change how ContextSage counts tokens, decides what to
preserve, reports what it did, or talks to an agent framework. Every class
here is an `abc.ABC`: ContextSage checks ``isinstance`` when it is configured,
so a missing method fails at construction rather than mid-run.

The summary model itself is a parsefabric `parsefabric.LanguageModel`, and
content parsing is customized with parsefabric's own extension points; see
`contextsage.ParsingOptions`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from contextsage.errors import ConfigurationError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from contextsage.events import SummarizationEvent
    from contextsage.messages import Message

__all__ = [
    "EventSink",
    "FrameworkAdapter",
    "JSONCompaction",
    "PreservationPolicy",
    "PreservationThresholds",
    "TokenCounter",
]


class TokenCounter(ABC):
    """Counts the tokens a list of messages occupies in a model's context.

    Implement `count` with the model's own tokenizer when exact budgets
    matter. The engine counts the whole history before every model call, so
    cache per message when counting is expensive, as
    `contextsage.TokenizerTokenCounter` does.
    """

    @abstractmethod
    async def count(self, messages: Sequence[Message]) -> int:
        """Return the number of tokens ``messages`` occupy.

        Args:
            messages: Messages in history order.

        Returns:
            A non-negative token count.
        """


class EventSink(ABC):
    """Receives one `contextsage.SummarizationEvent` per rewritten history.

    Implement `emit`; override `flush` and `close` if the destination buffers
    events or holds a connection. A sink that raises is logged and skipped:
    observability never fails an agent run.
    """

    @abstractmethod
    async def emit(self, event: SummarizationEvent) -> None:
        """Deliver one event.

        Args:
            event: Aggregate, content-free record of one summarization.
        """

    async def flush(self) -> None:  # noqa: B027 - optional hook, no-op by default
        """Deliver buffered events. The default does nothing."""

    async def close(self) -> None:  # noqa: B027 - optional hook, no-op by default
        """Flush and release resources. The default does nothing."""


class JSONCompaction(StrEnum):
    """How far JSON documents may be compacted."""

    MINIFY = "minify"
    """Remove insignificant whitespace only."""
    COLLAPSE_RUNS = "collapse_runs"
    """Also replace runs of identical consecutive list items with
    ``{"__repeated__": n, "value": item}``, which loses nothing."""
    SAMPLE = "sample"
    """Also collapse identical items anywhere in a list and keep only the first
    and last five entries of long lists, with ``{"__omitted__": n}`` between.
    Applied only to compressible content; other content gets `COLLAPSE_RUNS`."""


@dataclass(frozen=True, slots=True)
class PreservationThresholds:
    """Importance cut-offs that map a content unit to a preservation level.

    Attributes:
        must: Importance at or above which a unit is must-preserve.
        should: Importance at or above which a unit is should-preserve.
        error_must: Lower must-preserve cut-off for units that report errors.

    Raises:
        ConfigurationError: If a value is outside ``[0, 1]`` or ``should`` is
            above ``must``.
    """

    must: float
    should: float
    error_must: float

    def __post_init__(self) -> None:
        for name in ("must", "should", "error_must"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not 0 <= value <= 1
            ):
                raise ConfigurationError(f"threshold {name!r} must be a number in [0, 1]")
        if self.should > self.must:
            raise ConfigurationError("threshold 'should' must not exceed 'must'")


class PreservationPolicy(ABC):
    """Decides how readily content is compacted and summarized away.

    Structural signals always win: user corrections, identifiers the user
    stated or that appear next to failures, and both sides of a contradiction
    are must-preserve under every policy, and repetitive content is always
    compressible. A policy sets the importance thresholds for everything else
    and how far JSON may be compacted.

    Use `contextsage.BalancedPolicy`, `contextsage.MaximumPreservationPolicy`
    or `contextsage.MaximumCompressionPolicy`, or subclass this.
    """

    @property
    def name(self) -> str:
        """Name reported in logs; the class name by default."""
        return type(self).__name__

    @property
    @abstractmethod
    def thresholds(self) -> PreservationThresholds:
        """The importance cut-offs of this policy."""

    @property
    @abstractmethod
    def json_compaction(self) -> JSONCompaction:
        """How far JSON documents may be compacted."""


class FrameworkAdapter[NativeT](ABC):
    """Converts an agent framework's messages to and from `contextsage.Message`.

    Implement `to_message` and `from_message`; `to_messages` and
    `from_messages` convert whole histories. Keep the framework object in
    `contextsage.Message.native` so that `from_message` can return it unchanged,
    or update it in place of rebuilding, when ContextSage did not rewrite it.

    `contextsage.integrations.langchain.LangChainAdapter` is the reference
    implementation.
    """

    @property
    def propagated_errors(self) -> tuple[type[BaseException], ...]:
        """Exceptions from the summary model that must reach the framework.

        ContextSage recovers from summary-model failures by trimming the
        history. Frameworks that signal control flow with exceptions, such as
        LangGraph interrupts, list those exception types here. The default is
        none.
        """
        return ()

    @abstractmethod
    def to_message(self, native: NativeT) -> Message:
        """Convert one framework message.

        Args:
            native: The framework's message.

        Returns:
            The neutral message, with ``native`` set to the original object.
        """

    @abstractmethod
    def from_message(self, message: Message) -> NativeT:
        """Convert one neutral message back to the framework's type.

        Args:
            message: A message from the rewritten history. Summaries and
                restated facts are new messages with no ``native`` object.

        Returns:
            The framework's message.
        """

    def to_messages(self, natives: Sequence[NativeT]) -> list[Message]:
        """Convert a framework history; see `to_message`."""
        return [self.to_message(native) for native in natives]

    def from_messages(self, messages: Sequence[Message]) -> list[NativeT]:
        """Convert a rewritten history back; see `from_message`."""
        return [self.from_message(message) for message in messages]
