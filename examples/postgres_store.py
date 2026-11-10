"""Keep summary lineage in PostgreSQL with a custom agxai `ProvenanceStore`.

Run: python examples/postgres_store.py

Requires ``psycopg[binary,pool]`` (part of the ``examples`` dependency group)
and a database URL in ``CONTEXTSAGE_POSTGRES_DSN``, for example
``postgresql://contextsage:contextsage@localhost:5432/contextsage``. Start one
with Podman:

    podman run --rm -d --name contextsage-postgres -p 5432:5432 \\
      -e POSTGRES_USER=contextsage -e POSTGRES_PASSWORD=contextsage \\
      -e POSTGRES_DB=contextsage docker.io/library/postgres:18

ContextSage records lineage in whatever store the agxai runtime has
registered; the default keeps it in memory. This store is agxai's PostgreSQL
reference store: one JSONB table, keyed and indexed for tenant and run
isolation, written with idempotent upserts. It also overrides ``lineage`` with
one recursive SQL query. The script summarizes a conversation twice, closes
everything, and then reads the lineage back through a new runtime, as a
separate process (an audit job, say) would.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from importlib import import_module
from typing import TYPE_CHECKING, Any, ClassVar, cast, override

from _shared import ScriptedModel
from agxai import Execution, ProvenanceLink, ProvenanceStore, StoreFilter
from agxai.core import XAIEvent

from contextsage import ContextSummarizer, Message, create_agxai_runtime

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator, Sequence

    from agxai import ExecutionContext
    from agxai.core import CanonicalEvent, StoreQuery

    type StoredItem = Execution | ProvenanceLink | CanonicalEvent

SCHEMA = """
CREATE TABLE IF NOT EXISTS agxai_records (
    application_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    run_id UUID NOT NULL,
    record_type TEXT NOT NULL,
    record_id TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    PRIMARY KEY (application_id, tenant_id, run_id, record_type, record_id)
);
CREATE INDEX IF NOT EXISTS agxai_tenant_time_idx
    ON agxai_records (application_id, tenant_id, timestamp);
CREATE INDEX IF NOT EXISTS agxai_link_target_idx
    ON agxai_records (application_id, tenant_id, run_id, (payload->>'target_id'))
    WHERE record_type = 'ProvenanceLink';
"""
_ORDER = "ORDER BY timestamp, COALESCE((payload->>'sequence')::int, -1), payload->>'id'"
_MODELS: dict[str, type[Execution | ProvenanceLink | XAIEvent]] = {
    model.__name__: model for model in (Execution, ProvenanceLink, *XAIEvent.__subclasses__())
}
_LINEAGE = """
WITH RECURSIVE walk(depth, entity_id, payload, timestamp) AS (
    SELECT 1, payload->>'source_id', payload, timestamp
    FROM agxai_records
    WHERE record_type = 'ProvenanceLink'
      AND application_id = %(application_id)s AND tenant_id = %(tenant_id)s
      AND run_id = %(run_id)s AND payload->>'target_id' = %(entity_id)s
  UNION ALL
    SELECT walk.depth + 1, link.payload->>'source_id', link.payload, link.timestamp
    FROM walk
    JOIN agxai_records AS link
      ON link.record_type = 'ProvenanceLink'
     AND link.application_id = %(application_id)s AND link.tenant_id = %(tenant_id)s
     AND link.run_id = %(run_id)s AND link.payload->>'target_id' = walk.entity_id
    WHERE walk.depth < %(max_depth)s
)
CYCLE entity_id SET is_cycle USING path
SELECT payload FROM (
    SELECT DISTINCT ON (payload->>'id') payload, depth, timestamp
    FROM walk WHERE NOT is_cycle
    ORDER BY payload->>'id', depth
) AS links
ORDER BY depth, timestamp, payload->>'id'
"""


class _SingleConnection:
    """Provide the pool's small interface using one serialized async connection."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._connection: Any = None
        self._lock = asyncio.Lock()

    async def open(self) -> None:
        connection_class = import_module("psycopg").AsyncConnection
        self._connection = await connection_class.connect(self._dsn)

    @asynccontextmanager
    async def connection(self) -> AsyncGenerator[Any, None]:
        if self._connection is None:
            raise RuntimeError("PostgresProvenanceStore is not open")
        async with self._lock, self._connection.transaction():
            yield self._connection

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None


def _record_types(item_type: type[Any] | None) -> list[str] | None:
    """Return the stored type names a `StoreFilter.item_type` matches, subclasses included."""
    if item_type is None:
        return None
    return [name for name, model in _MODELS.items() if issubclass(model, item_type)]


def _decode(record_type: str, payload: Any) -> StoredItem:
    model = _MODELS.get(record_type)
    if model is None:
        raise ValueError(f"unsupported record type {record_type!r}")
    data = json.loads(payload) if isinstance(payload, str) else payload
    return cast("StoredItem", model.model_validate(data))


def _link(payload: Any) -> ProvenanceLink:
    return ProvenanceLink.model_validate(
        json.loads(payload) if isinstance(payload, str) else payload
    )


class PostgresProvenanceStore(ProvenanceStore):
    """A JSONB-backed store with indexed tenant and run isolation and idempotent upserts.

    Call `open` once before use. Other platforms use psycopg's asynchronous
    pool; Windows uses one serialized async connection.
    """

    SCHEMA: ClassVar[str] = SCHEMA
    """The DDL that `open` runs: the table and its indexes, all ``IF NOT EXISTS``."""

    def __init__(self, dsn: str, *, pool: Any | None = None) -> None:
        """Create a store for ``dsn``, or around an existing ``AsyncConnectionPool``.

        A pool passed in is owned by the caller and is not closed by `close`.
        """
        self._owns_pool = pool is None
        if pool is None:
            if sys.platform == "win32":
                pool = _SingleConnection(dsn)
            else:
                pool = import_module("psycopg_pool").AsyncConnectionPool(dsn, open=False)
        self._pool: Any = pool

    async def open(self, *, create_schema: bool = True) -> None:
        """Open the pool and, unless ``create_schema`` is false, create the schema."""
        await self._pool.open()
        if not create_schema:
            return
        try:
            async with self._pool.connection() as connection:
                await connection.execute(SCHEMA)
        except BaseException:
            if self._owns_pool:
                await self._pool.close()
            raise

    @override
    async def write(self, item: StoredItem) -> None:
        """Insert or replace ``item``."""
        context = item.context
        async with self._pool.connection() as connection:
            await connection.execute(
                """
                INSERT INTO agxai_records
                    (application_id, tenant_id, run_id, record_type, record_id, timestamp, payload)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (application_id, tenant_id, run_id, record_type, record_id)
                DO UPDATE SET timestamp = EXCLUDED.timestamp, payload = EXCLUDED.payload
                """,
                (
                    context.application_id,
                    context.tenant_id,
                    context.run_id,
                    type(item).__name__,
                    str(item.id),
                    item.timestamp,
                    item.model_dump_json(),
                ),
            )

    @override
    async def get(self, entity_id: str, *, context: ExecutionContext) -> StoredItem | None:
        """Return the record whose ``id`` is ``entity_id`` in the context's run, if any."""
        async with self._pool.connection() as connection:
            rows = await (
                await connection.execute(
                    "SELECT record_type, payload FROM agxai_records "
                    "WHERE application_id = %s AND tenant_id = %s AND run_id = %s "
                    "AND record_id = %s LIMIT 2",
                    (context.application_id, context.tenant_id, context.run_id, entity_id),
                )
            ).fetchall()
        if len(rows) > 1:
            raise LookupError("entity ID is ambiguous; use an isolation-aware query")
        return _decode(*rows[0]) if rows else None

    @override
    async def query(self, query: StoreQuery) -> AsyncIterator[StoredItem]:
        """Yield the records matching a `StoreFilter`."""
        if not isinstance(query, StoreFilter):
            raise TypeError("PostgresProvenanceStore requires StoreFilter")
        record_types = _record_types(query.item_type)
        async with self._pool.connection() as connection:
            rows = await (
                await connection.execute(
                    f"""
                    SELECT record_type, payload FROM agxai_records
                    WHERE application_id = %s AND tenant_id = %s
                      AND (%s::uuid IS NULL OR run_id = %s::uuid)
                      AND (%s::text[] IS NULL OR record_type = ANY(%s::text[]))
                    {_ORDER} LIMIT %s OFFSET %s
                    """,  # noqa: S608 - only the constant ORDER BY clause is interpolated
                    (
                        query.application_id,
                        query.tenant_id,
                        query.run_id,
                        query.run_id,
                        record_types,
                        record_types,
                        query.limit,
                        query.offset,
                    ),
                )
            ).fetchall()
        for row in rows:
            yield _decode(*row)

    @override
    async def parents(
        self, entity_id: str, *, context: ExecutionContext
    ) -> Sequence[ProvenanceLink]:
        """Return the links whose target is ``entity_id`` within the context's run."""
        return await self._links(entity_id, context, "target_id")

    @override
    async def children(
        self, entity_id: str, *, context: ExecutionContext
    ) -> Sequence[ProvenanceLink]:
        """Return the links whose source is ``entity_id`` within the context's run."""
        return await self._links(entity_id, context, "source_id")

    @override
    async def lineage(
        self, entity_id: str, *, context: ExecutionContext, max_depth: int = 100
    ) -> Sequence[ProvenanceLink]:
        """Return every upstream link of ``entity_id`` with one recursive query.

        Like the inherited walk, links are nearest first, each link appears
        once, and cycles terminate; links at the same depth are ordered by time.
        """
        if max_depth < 1:
            raise ValueError("max_depth must be positive")
        parameters = {
            "application_id": context.application_id,
            "tenant_id": context.tenant_id,
            "run_id": context.run_id,
            "entity_id": entity_id,
            "max_depth": max_depth,
        }
        async with self._pool.connection() as connection:
            rows = await (await connection.execute(_LINEAGE, parameters)).fetchall()
        return tuple(_link(row[0]) for row in rows)

    @override
    async def delete_run(self, context: ExecutionContext) -> int:
        """Delete every record of the context's run in one statement; return the count."""
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                "DELETE FROM agxai_records "
                "WHERE application_id = %s AND tenant_id = %s AND run_id = %s",
                (context.application_id, context.tenant_id, context.run_id),
            )
        return cursor.rowcount

    @override
    async def close(self) -> None:
        """Close the connection pool if this store created it."""
        if self._owns_pool:
            await self._pool.close()

    async def _links(
        self, entity_id: str, context: ExecutionContext, field: str
    ) -> tuple[ProvenanceLink, ...]:
        async with self._pool.connection() as connection:
            rows = await (
                await connection.execute(
                    f"""
                    SELECT payload FROM agxai_records
                    WHERE record_type = 'ProvenanceLink'
                      AND application_id = %s AND tenant_id = %s AND run_id = %s
                      AND payload->>%s = %s
                    {_ORDER}
                    """,  # noqa: S608 - only the constant ORDER BY clause is interpolated
                    (context.application_id, context.tenant_id, context.run_id, field, entity_id),
                )
            ).fetchall()
        return tuple(_link(row[0]) for row in rows)


THREAD = "claim-5521"


def turn(index: int) -> list[Message]:
    """One question about an insurance claim and its answer."""
    return [
        Message(
            "user", f"Question {index} about claim CLM-{5520 + index}.", id=f"{THREAD}-user-{index}"
        ),
        Message("assistant", f"Answer {index}.", id=f"{THREAD}-assistant-{index}"),
    ]


async def summarize_conversation(dsn: str) -> str:
    """Summarize a conversation twice and return the latest summary ID."""
    store = PostgresProvenanceStore(dsn)
    await store.open()
    runtime = create_agxai_runtime(application_id="claims", tenant_id="acme", store=store)
    try:
        async with ContextSummarizer(
            ScriptedModel("Summary of the claim discussion."),
            trigger=("messages", 5),
            keep=("messages", 2),
            runtime=runtime,
        ) as summarizer:
            history = turn(1) + turn(2) + turn(3)
            summary_id = ""
            for more in ([], turn(4) + turn(5)):
                history += more
                result = await summarizer.summarize(history, thread_id=THREAD)
                if result is None or result.event.summary_id is None:
                    raise SystemExit("The history did not trigger summarization.")
                history = list(result.messages)
                summary_id = result.event.summary_id
                print(
                    f"summarized {result.event.input_messages} messages, "
                    f"generation {result.event.generation}"
                )
            return summary_id
    finally:
        await runtime.close()


async def audit(dsn: str, summary_id: str) -> None:
    """Read the lineage back through a new store and runtime."""
    store = PostgresProvenanceStore(dsn)
    await store.open(create_schema=False)
    runtime = create_agxai_runtime(application_id="claims", tenant_id="acme", store=store)
    try:
        async with ContextSummarizer(ScriptedModel("unused"), runtime=runtime) as summarizer:
            links = await summarizer.lineage(summary_id, thread_id=THREAD)
            print(f"lineage read back from PostgreSQL: {len(links)} links")
            for link in links:
                source = str(link.source_id).removeprefix(f"{THREAD}-")
                if str(link.source_id) == source:
                    source = "earlier summary"
                target = (
                    "latest summary" if str(link.target_id) == summary_id else "earlier summary"
                )
                print(f"  {source} -> {target}")
            deleted = await summarizer.delete_lineage(thread_id=THREAD)
            print(f"deleted {deleted} records of the thread")
    finally:
        await runtime.close()


async def main() -> None:
    dsn = os.getenv("CONTEXTSAGE_POSTGRES_DSN")
    if not dsn:
        raise SystemExit(
            "Set CONTEXTSAGE_POSTGRES_DSN to a PostgreSQL URL, for example "
            "postgresql://contextsage:contextsage@localhost:5432/contextsage"
        )
    summary_id = await summarize_conversation(dsn)
    await audit(dsn, summary_id)


if __name__ == "__main__":
    # psycopg's asynchronous mode needs a selector event loop on Windows.
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None)
