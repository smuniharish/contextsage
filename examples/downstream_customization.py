"""Customize every extension point ContextSage inherits from parsefabric and agxai.

Run: python examples/downstream_customization.py

ContextSage is built on two packages, and exposes their extension points
instead of hiding them:

- parsefabric parses messages and counts tokens. `TokenizerTokenCounter` takes
  any parsefabric ``Tokenizer``; `ParsingOptions` takes a JSON codec, a code
  detector, a parser registry, a lifecycle ``ObservabilitySink`` and an
  ``ExecutionBackend``.
- agxai records summary provenance. `create_agxai_runtime` takes the
  identity, a ``ProvenanceStore``, an ``ObservabilityProvider``, a
  ``CapturePolicy``, and every other agxai extension point.

Every component below is a subclass of the downstream package's abstract base
class, and none of them changes what ContextSage does with the history.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from typing import TYPE_CHECKING, Any, override

from _shared import ScriptedModel
from agxai import (
    CapturePolicy,
    DefaultCapturePolicy,
    InMemoryProvenanceStore,
    ObservabilityProvider,
    PolicyDecision,
)
from parsefabric import StrictJSONCodec
from parsefabric.compression import Tokenizer
from parsefabric.execution import AsyncExecutionBackend
from parsefabric.observability import ObservabilitySink

from contextsage import (
    ContextSummarizer,
    Message,
    ParsingOptions,
    TokenizerTokenCounter,
    ToolCall,
    create_agxai_runtime,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from agxai import Execution, ProvenanceLink
    from agxai.core import CanonicalEvent
    from parsefabric.observability import LifecycleEvent


class WordTokenizer(Tokenizer):
    """Count whitespace-separated words, standing in for a model's tokenizer."""

    @override
    async def count(self, text: str) -> int:
        return len(text.split())


class InlineBackend(AsyncExecutionBackend):
    """Run analysis on the event loop and count calls; a real backend may use a process pool."""

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    @override
    async def run(self, function: Callable[..., Any], /, *args: object, **kwargs: object) -> Any:
        self.calls += 1
        return await super().run(function, *args, **kwargs)

    @override
    async def shutdown(self) -> None:
        print("backend: shut down by its owner")
        await super().shutdown()


class LifecycleCounter(ObservabilitySink):
    """Count parsefabric's parsing lifecycle events by name."""

    def __init__(self) -> None:
        self.names: Counter[str] = Counter()

    @override
    async def emit(self, event: LifecycleEvent) -> None:
        self.names[event.name] += 1


class CountingStore(InMemoryProvenanceStore):
    """An in-memory store that counts what it is asked to write."""

    def __init__(self) -> None:
        super().__init__()
        self.writes: Counter[str] = Counter()

    @override
    async def write(self, item: Execution | ProvenanceLink | CanonicalEvent) -> None:
        self.writes[type(item).__name__] += 1
        await super().write(item)


class AuditedCapture(CapturePolicy):
    """Allow every event, as agxai's default policy does, and remember what was allowed."""

    def __init__(self) -> None:
        self._default = DefaultCapturePolicy()
        self.allowed: Counter[str] = Counter()

    @override
    async def evaluate(self, event: CanonicalEvent) -> PolicyDecision:
        decision = await self._default.evaluate(event)
        self.allowed[type(event).__name__] += decision.allowed
        return decision


class EventCounter(ObservabilityProvider):
    """Count the canonical agxai events emitted, standing in for Langfuse or LangSmith."""

    def __init__(self) -> None:
        self.emitted = 0

    @override
    async def emit(self, event: CanonicalEvent) -> None:
        self.emitted += 1


HISTORY = [
    Message("user", "Order ORD-3101 is stuck in fulfilment.", id="u1"),
    Message("assistant", "", id="a1", tool_calls=(ToolCall("c1", "fulfilment_status", {}),)),
    Message(
        "tool",
        '{"order": "ORD-3101", "steps": ' + str(["picked"] * 30).replace("'", '"') + "}",
        id="t1",
        tool_call_id="c1",
    ),
    Message("assistant", "ORD-3101 is waiting for a carrier slot.", id="a2"),
    Message("user", "Book the next carrier slot.", id="u2"),
]


async def main() -> None:
    backend = InlineBackend()
    lifecycle = LifecycleCounter()
    store = CountingStore()
    capture = AuditedCapture()
    observability = EventCounter()
    runtime = create_agxai_runtime(
        application_id="fulfilment",
        tenant_id="acme",
        graph_id="support-agent",
        store=store,
        capture_policy=capture,
        observability=observability,
    )
    try:
        async with ContextSummarizer(
            ScriptedModel("ORD-3101 is waiting for a carrier slot."),
            trigger=("messages", 5),
            keep=("messages", 2),
            token_counter=TokenizerTokenCounter(WordTokenizer(), tokens_per_message=1),
            parsing=ParsingOptions(
                json_codec=StrictJSONCodec(),
                sink=lifecycle,
                backend=backend,
                max_concurrency=2,
            ),
            runtime=runtime,
        ) as summarizer:
            # Inside an agxai run (as in an agxai-instrumented agent), the summary
            # is also recorded as a memory write that passes the capture policy
            # and reaches the observability provider.
            run = await runtime.start_run({"configurable": {"thread_id": "ticket-88"}})
            with runtime.activate_run(run):
                result = await summarizer.summarize(HISTORY, thread_id="ticket-88")
            await runtime.finish_run(run)
            if result is None or result.event.summary_id is None:
                raise SystemExit("The history did not trigger summarization.")
            links = await summarizer.lineage(result.event.summary_id, thread_id="ticket-88")
    finally:
        await runtime.close()
        await backend.shutdown()

    event = result.event
    print(f"tokens counted in words: {event.input_tokens} -> {event.output_tokens}")
    print(f"analysis steps on the custom backend: {backend.calls > 0}")
    print(f"parsefabric lifecycle events: {sorted(lifecycle.names)}")
    print(f"store writes: {dict(sorted(store.writes.items()))}")
    print(f"capture policy allowed: {dict(sorted(capture.allowed.items()))}")
    print(f"observability events: {observability.emitted > 0}")
    print(f"lineage links for summary: {len(links)}")
    print(f"recorded under: {runtime.application_id}/{runtime.tenant_id}/{runtime.graph_id}")


if __name__ == "__main__":
    asyncio.run(main())
