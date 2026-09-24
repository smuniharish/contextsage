"""langgraph-xai provenance/evidence integration.

ContextIQ uses ``langgraph-xai`` as a direct dependency for tracking
provenance links between original context units, the evidence used, and the
resulting summary — without duplicating its provenance/evidence data model.
Provenance recording is best-effort: a failure here must
never abort a summarization operation, so all methods
degrade to a no-op and surface the failure only through the returned
:class:`ProvenanceOutcome`.

Each source message is linked directly to the summary via a single
``ProvenanceLink`` (``source_id=message_id``), with the evidence
description (kind, summary text) carried in the link's own ``metadata``
field rather than as a separately stored ``Evidence`` record: langgraph-xai's
``ProvenanceStore.write()`` contract (see ``ProvenanceStore`` in
``langgraph_xai.core.protocols``) only accepts
``Execution | ProvenanceLink | CanonicalEvent`` — ``Evidence`` is a value
object, not an independently storable entity — so linking directly (a
reference, not a payload copy) is both simpler and the
only approach that is correct against every ``ProvenanceStore``
implementation, not just the lenient in-memory default.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from langgraph_xai import (
    EvidenceType,
    ExecutionContext,
    InMemoryProvenanceStore,
    ProvenanceLink,
)

from contextiq.exceptions import ProvenanceError


@dataclass(slots=True)
class ProvenanceOutcome:
    """Result of a best-effort provenance recording attempt."""

    recorded: bool
    link_ids: tuple[str, ...] = field(default_factory=tuple)
    error: str | None = None


class ProvenanceManager:
    """Records source -> summary provenance links via langgraph-xai.

    Uses an in-memory store by default; a production deployment may supply
    any store implementing langgraph-xai's ``ProvenanceStore`` protocol
    (e.g. ``PostgresProvenanceStore``) without any change to ContextIQ code.
    """

    def __init__(
        self,
        *,
        application_id: str = "contextiq",
        tenant_id: str = "default",
        graph_id: str = "agent",
        run_id: UUID | None = None,
        store: InMemoryProvenanceStore | None = None,
    ) -> None:
        self._store = store or InMemoryProvenanceStore()
        self._application_id = application_id
        self._tenant_id = tenant_id
        self._graph_id = graph_id
        # `ExecutionContext.run_id` defaults to a fresh random UUID on every
        # construction. Pinning one run_id for this manager's lifetime is
        # required for correctness: langgraph-xai's stores scope every
        # lineage query by (application_id, tenant_id, run_id), so writing
        # and later querying with two different auto-generated run_ids would
        # silently make every lineage lookup return nothing.
        self._run_id = run_id or uuid4()

    def _context(self) -> ExecutionContext:
        return ExecutionContext(
            application_id=self._application_id,
            tenant_id=self._tenant_id,
            graph_id=self._graph_id,
            run_id=self._run_id,
        )

    async def arecord_summary_provenance(
        self,
        *,
        source_message_ids: tuple[str, ...],
        summary_id: str,
    ) -> ProvenanceOutcome:
        """Link each source message directly to the resulting summary."""
        try:
            context = self._context()
            link_ids: list[str] = []
            for message_id in source_message_ids:
                link = ProvenanceLink(
                    source_id=message_id,
                    target_id=summary_id,
                    relation="derived_from",
                    context=context,
                    metadata={
                        "evidence_type": str(EvidenceType.TOOL_RESULT),
                        "summary": "source message compressed during summarization",
                    },
                )
                await self._store.write(link)
                link_ids.append(str(link.id))
            return ProvenanceOutcome(recorded=True, link_ids=tuple(link_ids))
        except Exception as exc:
            return ProvenanceOutcome(recorded=False, error=str(exc))

    def record_summary_provenance(
        self,
        *,
        source_message_ids: tuple[str, ...],
        summary_id: str,
    ) -> ProvenanceOutcome:
        """Synchronous convenience wrapper around :meth:`arecord_summary_provenance`.

        Best-effort: if called from within a running event loop (where a
        blocking ``asyncio.run`` would fail), provenance recording is
        skipped rather than raising, since it must never interrupt the main
        summarization flow.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.arecord_summary_provenance(
                    source_message_ids=source_message_ids, summary_id=summary_id
                )
            )
        return ProvenanceOutcome(
            recorded=False,
            error="cannot run sync provenance recording inside an active event loop",
        )

    async def alineage(self, entity_id: str) -> tuple[ProvenanceLink, ...]:
        try:
            return tuple(await self._store.lineage(entity_id, context=self._context()))
        except Exception as exc:
            raise ProvenanceError(f"lineage lookup failed: {exc}") from exc

    async def aclose(self) -> None:
        with contextlib.suppress(Exception):
            await self._store.close()
