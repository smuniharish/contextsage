"""Token budget, trigger evaluation and the size of the kept window."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from contextsage.errors import ConfigurationError

DEFAULT_MAXIMUM_CONTEXT_TOKENS = 128_000
_KINDS = ("tokens", "messages", "fraction")

type Clause = tuple[tuple[str, float], ...]
type Window = tuple[Literal["messages"], int] | tuple[Literal["tokens"], int]
"""How much recent history stays verbatim, in messages or tokens."""


def resolve_keep(keep: object, maximum_context_tokens: int) -> Window:
    """Return the kept window, with a fraction converted to tokens.

    Args:
        keep: ``("messages", n)``, ``("tokens", n)`` or ``("fraction", f)``.
        maximum_context_tokens: The context window a fraction is a share of.

    Returns:
        The window in messages or tokens.

    Raises:
        ConfigurationError: If ``keep`` is malformed.
    """
    match keep:
        case ("messages", int() as count) if not isinstance(count, bool) and count > 0:
            return ("messages", count)
        case ("tokens", int() as count) if not isinstance(count, bool) and count > 0:
            return ("tokens", count)
        case ("fraction", int() | float() as share) if (
            not isinstance(share, bool) and 0 < share <= 1
        ):
            return ("tokens", max(1, int(maximum_context_tokens * share)))
        case _:
            raise ConfigurationError(
                "keep must be ('messages', n) or ('tokens', n) with a positive "
                f"integer n, or ('fraction', f) with 0 < f <= 1; got {keep!r}"
            )


def resolve_maximum_context_tokens(model: object, explicit: int | None) -> int:
    """Return the context window to budget against.

    Args:
        model: The chat model; its LangChain model profile is consulted.
        explicit: A caller-supplied value, which always wins.

    Returns:
        ``explicit``, else the profile's ``max_input_tokens``, else 128,000.

    Raises:
        ConfigurationError: If ``explicit`` is not a positive integer.
    """
    if explicit is not None:
        if isinstance(explicit, bool) or not isinstance(explicit, int) or explicit <= 0:
            raise ConfigurationError(
                "maximum_context_tokens must be a positive integer"
            )
        return explicit
    profile = getattr(model, "profile", None)
    if isinstance(profile, Mapping):
        value = profile.get("max_input_tokens")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    return DEFAULT_MAXIMUM_CONTEXT_TOKENS


@dataclass(frozen=True, slots=True)
class Budget:
    """Explicit accounting of the context window.

    Attributes:
        maximum_context_tokens: The model's context window.
        reserved_output_tokens: Tokens kept free for the model's response.
        safety_margin: Fraction of the window held back as a buffer.
        summarization_overhead_tokens: Tokens kept free for the summarization
            call's own prompt and for the system prompt and tool schemas that
            are not part of the message history.
    """

    maximum_context_tokens: int
    reserved_output_tokens: int
    safety_margin: float
    summarization_overhead_tokens: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.reserved_output_tokens, bool)
            or not isinstance(self.reserved_output_tokens, int)
            or self.reserved_output_tokens < 0
        ):
            raise ConfigurationError(
                "reserved_output_tokens must be a non-negative integer"
            )
        if (
            isinstance(self.summarization_overhead_tokens, bool)
            or not isinstance(self.summarization_overhead_tokens, int)
            or self.summarization_overhead_tokens < 0
        ):
            raise ConfigurationError(
                "summarization_overhead_tokens must be a non-negative integer"
            )
        if (
            isinstance(self.safety_margin, bool)
            or not isinstance(self.safety_margin, (int, float))
            or not 0 <= self.safety_margin < 1
        ):
            raise ConfigurationError("safety_margin must be a number in [0, 1)")
        if self.available_tokens <= 0:
            raise ConfigurationError(
                "the reserved output tokens, safety margin and summarization "
                "overhead leave no room for input in a "
                f"{self.maximum_context_tokens}-token window"
            )

    @property
    def safety_margin_tokens(self) -> int:
        """The safety margin in tokens."""
        return round(self.maximum_context_tokens * self.safety_margin)

    @property
    def available_tokens(self) -> int:
        """Tokens available for the message history."""
        return (
            self.maximum_context_tokens
            - self.reserved_output_tokens
            - self.safety_margin_tokens
            - self.summarization_overhead_tokens
        )


@dataclass(frozen=True, slots=True)
class Decision:
    """Why summarization is required and by how much the history is over."""

    reason: str
    overflow_tokens: int


def _threshold(kind: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(f"trigger {kind!r} threshold must be a number")
    if kind == "fraction":
        if not 0 < value <= 1:
            raise ConfigurationError("trigger 'fraction' must be in (0, 1]")
        return float(value)
    if not isinstance(value, int) or value <= 0:
        raise ConfigurationError(
            f"trigger {kind!r} threshold must be a positive integer"
        )
    return float(value)


def _clause(spec: object) -> Clause:
    match spec:
        case (str() as kind, value) if kind in _KINDS:
            return ((kind, _threshold(kind, value)),)
        case tuple():
            raise ConfigurationError(
                "a trigger tuple must be ('tokens' | 'messages' | 'fraction', value)"
            )
        case Mapping() if spec and all(key in _KINDS for key in spec):
            return tuple(
                (key, _threshold(key, spec[key])) for key in _KINDS if key in spec
            )
        case Mapping():
            raise ConfigurationError(
                "a trigger clause must map 'tokens', 'messages' or 'fraction' to values"
            )
        case _:
            raise ConfigurationError(f"unsupported trigger: {spec!r}")


class Trigger:
    """Decides whether the history needs summarizing.

    Accepts LangChain's ``SummarizationMiddleware`` trigger forms: one
    ``(kind, value)`` tuple, one clause mapping whose conditions must all hold,
    or a list of either where any item may hold. ``None`` means "when the
    history no longer fits the budget".

    Args:
        spec: The trigger specification.
        budget: The budget used by fractions and by ``None``.

    Raises:
        ConfigurationError: If ``spec`` is malformed.
    """

    def __init__(self, spec: object, budget: Budget) -> None:
        self._budget = budget
        if spec is None:
            self._clauses: tuple[Clause, ...] | None = None
        elif isinstance(spec, Sequence) and not isinstance(spec, (tuple, str)):
            if not spec:
                raise ConfigurationError("a trigger list must not be empty")
            self._clauses = tuple(_clause(item) for item in spec)
        else:
            self._clauses = (_clause(spec),)

    def evaluate(self, *, tokens: int, messages: int) -> Decision | None:
        """Return why summarization is required, or ``None`` if it is not.

        Args:
            tokens: Tokens in the current history.
            messages: Messages in the current history.

        Returns:
            The decision, or ``None`` when no trigger condition holds.
        """
        available = self._budget.available_tokens
        if self._clauses is None:
            if tokens <= available:
                return None
            return Decision(
                f"{tokens} tokens exceed the {available}-token input budget",
                tokens - available,
            )
        for clause in self._clauses:
            reasons: list[str] = []
            overflow = 0
            for kind, threshold in clause:
                if kind == "messages":
                    if messages < threshold:
                        break
                    reasons.append(f"{messages} messages >= {int(threshold)}")
                    continue
                limit = (
                    round(self._budget.maximum_context_tokens * threshold)
                    if kind == "fraction"
                    else int(threshold)
                )
                if tokens < limit:
                    break
                reasons.append(f"{tokens} tokens >= {limit}")
                overflow = max(overflow, tokens - limit)
            else:
                if overflow == 0:
                    overflow = max(tokens - available, 0)
                return Decision(" and ".join(reasons), overflow)
        return None
