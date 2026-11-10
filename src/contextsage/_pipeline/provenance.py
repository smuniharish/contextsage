"""Recording summary lineage in an agxai runtime's provenance store."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
from uuid import NAMESPACE_URL, uuid5

from agxai import ExecutionContext, MemoryOperation, ProvenanceLink, ProvenanceStore

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from agxai import XAIRuntime

logger = logging.getLogger("contextsage")

RELATION = "derived_from"
MEMORY_NAMESPACE = "contextsage"
_RUN_NAMESPACE = uuid5(NAMESPACE_URL, "https://github.com/smuniharish/contextsage")


class ProvenanceRecorder:
    """Writes one ``derived_from`` link per summarized message.

    Links are scoped to a run whose ID is derived from the thread ID, so the
    lineage of any summary in a thread can be queried later without knowing
    which agent run produced it. Recording is best effort: a store failure is
    logged and never interrupts the caller.

    Args:
        runtime: The agxai runtime whose registered ``ProvenanceStore`` and
            identity are used.
    """

    def __init__(self, runtime: XAIRuntime) -> None:
        self.runtime = runtime

    @property
    def store(self) -> ProvenanceStore:
        """The store currently registered on the runtime."""
        return self.runtime.registry.require(ProvenanceStore)

    def context(self, thread_id: str | None, graph_id: str | None = None) -> ExecutionContext:
        """Return the provenance scope of a conversation thread."""
        return ExecutionContext(
            application_id=self.runtime.application_id,
            tenant_id=self.runtime.tenant_id,
            graph_id=graph_id or self.runtime.graph_id,
            run_id=uuid5(_RUN_NAMESPACE, thread_id or ""),
            thread_id=thread_id,
        )

    async def record(
        self,
        *,
        source_ids: Sequence[str],
        summary_id: str,
        thread_id: str | None,
        graph_id: str | None,
        metadata: Mapping[str, object],
    ) -> None:
        """Link every source message to the summary that replaced it.

        Inside an instrumented agxai call, the summary is also recorded as a
        memory write of the active run.
        """
        context = self.context(thread_id, graph_id)
        store = self.store
        try:
            async with asyncio.TaskGroup() as group:
                for source_id in source_ids:
                    group.create_task(
                        store.write(
                            ProvenanceLink(
                                source_id=source_id,
                                target_id=summary_id,
                                relation=RELATION,
                                context=context,
                                metadata={"recorded_by": MEMORY_NAMESPACE},
                            )
                        )
                    )
            run = self.runtime.current_run
            if run is not None:
                await self.runtime.record_memory(
                    summary_id,
                    MemoryOperation.WRITE,
                    namespace=MEMORY_NAMESPACE,
                    metadata=metadata,
                    run=run,
                )
        except Exception:
            logger.warning(
                "contextsage could not record provenance for summary %s",
                summary_id,
                exc_info=True,
            )

    async def lineage(
        self, summary_id: str, thread_id: str | None, graph_id: str | None = None
    ) -> tuple[ProvenanceLink, ...]:
        """Return every upstream link of a summary, nearest first."""
        return tuple(
            await self.store.lineage(summary_id, context=self.context(thread_id, graph_id))
        )

    async def delete(self, thread_id: str | None) -> int:
        """Delete every link recorded for a thread and return how many records were removed."""
        return await self.store.delete_run(self.context(thread_id))
