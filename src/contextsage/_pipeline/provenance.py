"""Provenance links from summarized messages to their summary, via langgraph-xai."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import NAMESPACE_URL, uuid5

from langgraph_xai import ExecutionContext, ProvenanceLink

if TYPE_CHECKING:
    from collections.abc import Sequence

    from langgraph_xai import ProvenanceStore

logger = logging.getLogger("contextsage")

APPLICATION_ID = "contextsage"
TENANT_ID = "default"
DEFAULT_GRAPH_ID = "agent"
RELATION = "derived_from"
_RUN_NAMESPACE = uuid5(NAMESPACE_URL, "https://github.com/smuniharish/contextsage")


def execution_context(
    thread_id: str | None, graph_id: str | None = None
) -> ExecutionContext:
    """Return the provenance scope of a LangGraph thread.

    The run ID is derived deterministically from the thread ID, so the lineage
    of any summary in a thread can be queried later. Without a checkpointer
    there is no thread, and all summaries share one default scope.

    Args:
        thread_id: The LangGraph thread ID, if any.
        graph_id: The LangGraph graph ID, if known.

    Returns:
        The execution context links are written and queried in.
    """
    return ExecutionContext(
        application_id=APPLICATION_ID,
        tenant_id=TENANT_ID,
        graph_id=graph_id or DEFAULT_GRAPH_ID,
        run_id=uuid5(_RUN_NAMESPACE, thread_id or ""),
        thread_id=thread_id,
    )


class ProvenanceRecorder:
    """Writes one ``derived_from`` link per summarized message to a store.

    Recording is best effort: a store failure is logged and never interrupts
    the agent.

    Args:
        store: Any langgraph-xai ``ProvenanceStore``.
    """

    def __init__(self, store: ProvenanceStore) -> None:
        self.store = store

    async def record(
        self,
        *,
        source_ids: Sequence[str],
        summary_id: str,
        thread_id: str | None,
        graph_id: str | None,
    ) -> None:
        """Link every source message to the summary that replaced it."""
        context = execution_context(thread_id, graph_id)
        try:
            for source_id in source_ids:
                await self.store.write(
                    ProvenanceLink(
                        source_id=source_id,
                        target_id=summary_id,
                        relation=RELATION,
                        context=context,
                        metadata={"recorded_by": APPLICATION_ID},
                    )
                )
        except Exception:
            logger.warning(
                "contextsage could not record provenance for summary %s",
                summary_id,
                exc_info=True,
            )

    async def lineage(
        self, summary_id: str, thread_id: str | None
    ) -> tuple[ProvenanceLink, ...]:
        """Return every upstream link of a summary, nearest first."""
        return tuple(
            await self.store.lineage(summary_id, context=execution_context(thread_id))
        )
