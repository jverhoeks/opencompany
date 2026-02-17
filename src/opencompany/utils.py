"""Shared utilities for bridging sync/async contexts."""

import asyncio

_main_loop: asyncio.AbstractEventLoop | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Store a reference to the main event loop (call once at startup)."""
    global _main_loop
    _main_loop = loop


def _run_async(coro):
    """Run an async coroutine from a sync context (e.g. agent tools running in threads).

    Schedules the coroutine on the main event loop via run_coroutine_threadsafe.
    Falls back to creating a new event loop for non-threaded contexts (e.g. tests).
    """
    if _main_loop and _main_loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, _main_loop)
        return future.result(timeout=60)

    # Fallback for non-threaded contexts (e.g. tests)
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
