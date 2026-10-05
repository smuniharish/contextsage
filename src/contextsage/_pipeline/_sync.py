"""Run a coroutine to completion from synchronous code."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Coroutine
    from typing import Any


def run_sync[T](coroutine: Coroutine[Any, Any, T]) -> T:
    """Run ``coroutine`` and return its result.

    The coroutine runs on a private event loop, which never replaces the event
    loop the calling thread has set. When the calling thread is already running
    an event loop (for example a synchronous agent call made from a notebook),
    the coroutine runs in a worker thread instead, because a running loop
    cannot be re-entered.

    Args:
        coroutine: The coroutine to run; it is always awaited exactly once.

    Returns:
        The coroutine's result.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine, loop_factory=asyncio.new_event_loop)
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="contextsage") as pool:
        return pool.submit(
            asyncio.run, coroutine, loop_factory=asyncio.new_event_loop
        ).result()
