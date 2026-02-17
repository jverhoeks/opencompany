"""Shared utilities for bridging sync/async contexts."""

import asyncio


def _run_async(coro):
    """Run an async coroutine from a sync context (e.g. agent tools running in threads).

    Tries to find a running event loop to schedule the coroutine on.
    Falls back to creating a new event loop for non-threaded contexts (e.g. tests).
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result(timeout=60)
    except RuntimeError:
        pass

    # Fallback for non-threaded contexts (e.g. tests)
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
