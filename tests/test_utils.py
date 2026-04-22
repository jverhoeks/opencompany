"""Tests for opencompany/utils.py — set_main_loop and _run_async."""

import asyncio
from unittest.mock import MagicMock, patch

from opencompany.utils import _run_async, set_main_loop


def test_set_main_loop_stores_loop():
    """set_main_loop stores the loop reference in module state."""
    import opencompany.utils as mod

    original = mod._main_loop
    try:
        sentinel = MagicMock(spec=asyncio.AbstractEventLoop)
        set_main_loop(sentinel)
        assert mod._main_loop is sentinel
    finally:
        mod._main_loop = original


def test_run_async_fallback_creates_new_loop():
    """When no main loop is set, _run_async creates a new event loop."""
    import opencompany.utils as mod

    original = mod._main_loop
    try:
        mod._main_loop = None

        async def coro():
            return 42

        result = _run_async(coro())
        assert result == 42
    finally:
        mod._main_loop = original


def test_run_async_uses_main_loop_when_running():
    """When main loop is set and running, _run_async uses run_coroutine_threadsafe."""
    import opencompany.utils as mod

    original = mod._main_loop

    mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
    mock_loop.is_running.return_value = True

    mock_future = MagicMock()
    mock_future.result.return_value = "threaded-result"

    try:
        mod._main_loop = mock_loop

        async def coro():
            return "test"

        # Bind the coroutine explicitly so we can close it after the patched
        # ``run_coroutine_threadsafe`` short-circuits scheduling — otherwise
        # the live coroutine leaks and triggers "never awaited" warnings.
        c = coro()
        try:
            with patch("asyncio.run_coroutine_threadsafe", return_value=mock_future) as mock_rcts:
                result = _run_async(c)
        finally:
            c.close()

        assert result == "threaded-result"
        mock_rcts.assert_called_once()
        mock_future.result.assert_called_once_with(timeout=60)
    finally:
        mod._main_loop = original


def test_run_async_fallback_when_loop_not_running():
    """When main loop is set but not running, _run_async falls back to new loop."""
    import opencompany.utils as mod

    original = mod._main_loop

    mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
    mock_loop.is_running.return_value = False

    try:
        mod._main_loop = mock_loop

        async def coro():
            return 99

        result = _run_async(coro())
        assert result == 99
    finally:
        mod._main_loop = original
