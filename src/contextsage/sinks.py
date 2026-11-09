"""The built-in event sinks: logging, OpenTelemetry metrics, and fan-out."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, override

from opentelemetry import metrics

from contextsage.contracts import EventSink
from contextsage.errors import ConfigurationError

if TYPE_CHECKING:
    from collections.abc import Iterable

    from opentelemetry.metrics import Meter

    from contextsage.events import SummarizationEvent

__all__ = ["CompositeEventSink", "LoggingEventSink", "OpenTelemetryEventSink"]

_LOGGER = logging.getLogger("contextsage")


async def deliver(sink: EventSink, event: SummarizationEvent) -> None:
    """Emit ``event`` to ``sink``, logging instead of raising on sink errors."""
    try:
        await sink.emit(event)
    except Exception:
        _LOGGER.warning("contextsage event sink %s failed", type(sink).__name__, exc_info=True)


class LoggingEventSink(EventSink):
    """Log every event as one structured ``INFO`` record.

    The record's message is ``"contextsage summarization"`` and the event is
    attached as the ``contextsage`` attribute (``extra={"contextsage": ...}``),
    ready for a JSON log formatter. This is the default sink.

    Args:
        logger: Logger to write to. Defaults to the ``contextsage`` logger.
    """

    def __init__(self, logger: logging.Logger | None = None) -> None:
        if logger is not None and not isinstance(logger, logging.Logger):
            raise ConfigurationError("logger must be a logging.Logger")
        self._logger = logger or _LOGGER

    @override
    async def emit(self, event: SummarizationEvent) -> None:
        self._logger.info("contextsage summarization", extra={"contextsage": event.as_dict()})


class OpenTelemetryEventSink(EventSink):
    """Record every event as OpenTelemetry metrics.

    Instruments, all tagged with ``validation_status``, ``recovery_status`` and
    ``policy``:

    - ``contextsage.summarizations`` (counter): rewritten histories.
    - ``contextsage.input_tokens`` and ``contextsage.output_tokens``
      (histograms, ``{token}``): history size before and after.
    - ``contextsage.compression_ratio`` (histogram): output over input tokens.
    - ``contextsage.compacted_units`` (counter): units compacted
      deterministically.
    - ``contextsage.duration`` (histogram, ``ms``): time spent summarizing.

    ContextSage does not configure an OpenTelemetry SDK; without one, the
    API's no-op meter records nothing. Install ``contextsage[otel]`` for the
    SDK and the OTLP exporter. Spans are recorded by the engine itself.

    Args:
        meter: Meter to create the instruments on. Defaults to
            ``metrics.get_meter("contextsage")``.
    """

    def __init__(self, meter: Meter | None = None) -> None:
        meter = meter or metrics.get_meter("contextsage")
        self._summarizations = meter.create_counter(
            "contextsage.summarizations", unit="{summarization}", description="Rewritten histories."
        )
        self._input_tokens = meter.create_histogram(
            "contextsage.input_tokens", unit="{token}", description="Tokens before summarization."
        )
        self._output_tokens = meter.create_histogram(
            "contextsage.output_tokens", unit="{token}", description="Tokens after summarization."
        )
        self._ratio = meter.create_histogram(
            "contextsage.compression_ratio", unit="1", description="Output over input tokens."
        )
        self._compacted = meter.create_counter(
            "contextsage.compacted_units",
            unit="{unit}",
            description="Content units compacted deterministically.",
        )
        self._duration = meter.create_histogram(
            "contextsage.duration", unit="ms", description="Time spent summarizing."
        )

    @override
    async def emit(self, event: SummarizationEvent) -> None:
        attributes = {
            "validation_status": event.validation_status,
            "recovery_status": event.recovery_status,
            "policy": event.policy,
        }
        self._summarizations.add(1, attributes)
        self._input_tokens.record(event.input_tokens, attributes)
        self._output_tokens.record(event.output_tokens, attributes)
        self._ratio.record(event.compression_ratio, attributes)
        self._compacted.add(event.compacted_units, attributes)
        self._duration.record(event.latency_ms, attributes)


class CompositeEventSink(EventSink):
    """Deliver every event to several sinks, in order.

    A failing child sink is logged and skipped; the others still receive the
    event.

    Args:
        sinks: Sinks that receive every event.

    Raises:
        ConfigurationError: If an item is not an `EventSink`.
    """

    def __init__(self, sinks: Iterable[EventSink]) -> None:
        self._sinks = tuple(sinks)
        if not all(isinstance(sink, EventSink) for sink in self._sinks):
            raise ConfigurationError("composite sinks must be EventSink instances")

    @property
    def sinks(self) -> tuple[EventSink, ...]:
        """The child sinks, in delivery order."""
        return self._sinks

    @override
    async def emit(self, event: SummarizationEvent) -> None:
        for sink in self._sinks:
            await deliver(sink, event)

    @override
    async def flush(self) -> None:
        """Flush every child sink, then raise any failures together.

        Raises:
            ExceptionGroup: If one or more child sinks failed to flush.
        """
        await self._each("flush")

    @override
    async def close(self) -> None:
        """Close every child sink, then raise any failures together.

        Raises:
            ExceptionGroup: If one or more child sinks failed to close.
        """
        await self._each("close")

    async def _each(self, operation: str) -> None:
        errors: list[Exception] = []
        for sink in self._sinks:
            try:
                await getattr(sink, operation)()
            except Exception as error:
                errors.append(error)
        if errors:
            raise ExceptionGroup(f"{len(errors)} event sink(s) failed to {operation}", errors)
