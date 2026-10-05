from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import pytest
from langgraph_xai import InMemoryProvenanceStore

from contextsage._pipeline._sync import run_sync
from contextsage._pipeline.provenance import (
    APPLICATION_ID,
    DEFAULT_GRAPH_ID,
    RELATION,
    ProvenanceRecorder,
    execution_context,
)


def test_execution_context_is_deterministic_per_thread():
    first = execution_context("thread-1", "graph")
    again = execution_context("thread-1")
    other = execution_context("thread-2")
    default = execution_context(None)
    assert first.run_id == again.run_id != other.run_id != default.run_id
    assert isinstance(first.run_id, UUID)
    assert (first.application_id, first.graph_id, first.thread_id) == (
        APPLICATION_ID,
        "graph",
        "thread-1",
    )
    assert again.graph_id == DEFAULT_GRAPH_ID
    assert default.thread_id is None


def test_record_and_query_lineage_in_one_thread():
    recorder = ProvenanceRecorder(InMemoryProvenanceStore())

    async def scenario() -> tuple:
        await recorder.record(
            source_ids=("m1", "m2"), summary_id="s1", thread_id="t", graph_id=None
        )
        await recorder.record(
            source_ids=("s1", "m3"), summary_id="s2", thread_id="t", graph_id="g"
        )
        return await recorder.lineage("s2", "t"), await recorder.lineage("s2", "other")

    links, other_thread = asyncio.run(scenario())
    assert [(str(link.source_id), str(link.target_id)) for link in links] == [
        ("s1", "s2"),
        ("m3", "s2"),
        ("m1", "s1"),
        ("m2", "s1"),
    ]
    assert all(link.relation == RELATION for link in links)
    assert links[0].metadata == {"recorded_by": APPLICATION_ID}
    assert other_thread == ()


class BrokenStore(InMemoryProvenanceStore):
    async def write(self, item: object) -> None:
        raise ConnectionError("database unavailable")


def test_store_failures_are_logged_not_raised(caplog):
    recorder = ProvenanceRecorder(BrokenStore())
    with caplog.at_level(logging.WARNING, logger="contextsage"):
        asyncio.run(
            recorder.record(
                source_ids=("m1",), summary_id="s1", thread_id=None, graph_id=None
            )
        )
    assert "could not record provenance for summary s1" in caplog.text


async def value() -> int:
    return 7


def test_run_sync_without_a_running_loop():
    assert run_sync(value()) == 7


def test_run_sync_keeps_the_threads_event_loop():
    def scenario() -> bool:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            assert run_sync(value()) == 7
            return asyncio.get_event_loop() is loop
        finally:
            asyncio.set_event_loop(None)
            loop.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(scenario).result()


async def test_run_sync_inside_a_running_loop_uses_a_worker_thread():
    assert run_sync(value()) == 7


def test_run_sync_propagates_errors():
    async def fail() -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        run_sync(fail())
