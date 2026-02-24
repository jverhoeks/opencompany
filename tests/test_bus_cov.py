"""Extended tests for events/bus.py — connection lifecycle, subscribe loop, ping."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from opencompany.events import bus


# ---------------------------------------------------------------------------
# init_redis / close_redis / get_redis
# ---------------------------------------------------------------------------
async def test_init_redis_creates_pool_and_client():
    """init_redis sets module-level _pool and _redis."""
    # Reset module state
    bus._pool = None
    bus._redis = None

    mock_pool = MagicMock()
    mock_client = MagicMock()

    with (
        patch.object(
            bus.redis.ConnectionPool,
            "from_url",
            return_value=mock_pool,
        ),
        patch("opencompany.events.bus.redis.Redis", return_value=mock_client),
    ):
        await bus.init_redis()
        assert bus._pool is mock_pool
        assert bus._redis is mock_client

    # Cleanup
    bus._pool = None
    bus._redis = None


async def test_init_redis_is_idempotent():
    """Calling init_redis twice does not overwrite existing pool."""
    sentinel_pool = MagicMock()
    sentinel_redis = MagicMock()
    bus._pool = sentinel_pool
    bus._redis = sentinel_redis

    await bus.init_redis()

    assert bus._pool is sentinel_pool
    assert bus._redis is sentinel_redis

    # Cleanup
    bus._pool = None
    bus._redis = None


async def test_close_redis_cleans_up():
    """close_redis closes client and pool, resets to None."""
    mock_redis = AsyncMock()
    mock_pool = AsyncMock()
    bus._redis = mock_redis
    bus._pool = mock_pool

    await bus.close_redis()

    mock_redis.aclose.assert_awaited_once()
    mock_pool.aclose.assert_awaited_once()
    assert bus._redis is None
    assert bus._pool is None


async def test_close_redis_noop_when_not_initialized():
    """close_redis is safe to call when nothing is initialized."""
    bus._redis = None
    bus._pool = None

    await bus.close_redis()

    assert bus._redis is None
    assert bus._pool is None


async def test_get_redis_returns_existing():
    """get_redis returns the existing client without re-initialising."""
    sentinel = AsyncMock()
    bus._redis = sentinel

    result = await bus.get_redis()
    assert result is sentinel

    bus._redis = None


async def test_get_redis_initializes_lazily():
    """get_redis calls init_redis when _redis is None."""
    bus._redis = None
    bus._pool = None

    mock_pool = MagicMock()
    mock_client = AsyncMock()

    with (
        patch.object(
            bus.redis.ConnectionPool,
            "from_url",
            return_value=mock_pool,
        ),
        patch("opencompany.events.bus.redis.Redis", return_value=mock_client),
    ):
        result = await bus.get_redis()
        assert result is mock_client

    # Cleanup
    bus._pool = None
    bus._redis = None


# ---------------------------------------------------------------------------
# ping
# ---------------------------------------------------------------------------
async def test_ping_returns_true_when_reachable():
    mock_redis = AsyncMock()
    mock_redis.ping.return_value = True

    with patch("opencompany.events.bus.get_redis", return_value=mock_redis):
        assert await bus.ping() is True


async def test_ping_returns_false_on_error():
    with patch("opencompany.events.bus.get_redis", side_effect=Exception("down")):
        assert await bus.ping() is False


# ---------------------------------------------------------------------------
# _ensure_consumer_group
# ---------------------------------------------------------------------------
async def test_ensure_consumer_group_creates_group():
    mock_redis = AsyncMock()
    await bus._ensure_consumer_group(mock_redis)
    mock_redis.xgroup_create.assert_awaited_once_with(
        bus.STREAM_KEY, bus.GROUP_NAME, id="0", mkstream=True
    )


async def test_ensure_consumer_group_ignores_busygroup():
    """BUSYGROUP error is silently handled (group already exists)."""
    mock_redis = AsyncMock()
    mock_redis.xgroup_create.side_effect = bus.redis.ResponseError("BUSYGROUP already exists")
    await bus._ensure_consumer_group(mock_redis)  # should not raise


async def test_ensure_consumer_group_raises_other_errors():
    """Non-BUSYGROUP ResponseError is re-raised."""
    mock_redis = AsyncMock()
    mock_redis.xgroup_create.side_effect = bus.redis.ResponseError("OTHER error")
    with pytest.raises(bus.redis.ResponseError, match="OTHER"):
        await bus._ensure_consumer_group(mock_redis)


# ---------------------------------------------------------------------------
# subscribe — message processing loop
# ---------------------------------------------------------------------------
async def test_subscribe_processes_messages_and_acks():
    """subscribe reads messages, dispatches callback, and ACKs."""
    mock_redis = AsyncMock()
    callback = AsyncMock()

    payload = json.dumps({"type": "ticket.created", "data": {"id": 1}})
    # First call returns a message, second raises CancelledError to exit
    mock_redis.xreadgroup.side_effect = [
        [(bus.STREAM_KEY, [("msg-1", {"payload": payload})])],
        asyncio.CancelledError(),
    ]

    with (
        patch("opencompany.events.bus.get_redis", return_value=mock_redis),
        patch("opencompany.events.bus._ensure_consumer_group", new_callable=AsyncMock),
        pytest.raises(asyncio.CancelledError),
    ):
        await bus.subscribe(callback)

    callback.assert_awaited_once_with("ticket.created", {"id": 1})
    mock_redis.xack.assert_awaited_once_with(bus.STREAM_KEY, bus.GROUP_NAME, "msg-1")


async def test_subscribe_handles_empty_read():
    """subscribe resets backoff on empty read and continues."""
    mock_redis = AsyncMock()
    callback = AsyncMock()

    # Empty read, then cancel
    mock_redis.xreadgroup.side_effect = [
        None,
        asyncio.CancelledError(),
    ]

    with (
        patch("opencompany.events.bus.get_redis", return_value=mock_redis),
        patch("opencompany.events.bus._ensure_consumer_group", new_callable=AsyncMock),
        pytest.raises(asyncio.CancelledError),
    ):
        await bus.subscribe(callback)

    callback.assert_not_awaited()


async def test_subscribe_handles_callback_error():
    """Callback errors are logged but processing continues."""
    mock_redis = AsyncMock()
    callback = AsyncMock(side_effect=ValueError("boom"))

    payload = json.dumps({"type": "test.event", "data": {}})
    mock_redis.xreadgroup.side_effect = [
        [(bus.STREAM_KEY, [("msg-1", {"payload": payload})])],
        asyncio.CancelledError(),
    ]

    with (
        patch("opencompany.events.bus.get_redis", return_value=mock_redis),
        patch("opencompany.events.bus._ensure_consumer_group", new_callable=AsyncMock),
        pytest.raises(asyncio.CancelledError),
    ):
        await bus.subscribe(callback)

    # xack should NOT be called when callback errors
    mock_redis.xack.assert_not_awaited()


async def test_subscribe_retries_on_transient_error():
    """Transient read errors trigger backoff + reconnect."""
    mock_redis = AsyncMock()
    callback = AsyncMock()

    mock_redis.xreadgroup.side_effect = [
        ConnectionError("Redis gone"),
        asyncio.CancelledError(),
    ]

    reconnect_redis = AsyncMock()

    call_count = 0

    async def tracked_get():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_redis  # initial
        return reconnect_redis  # after error

    with (
        patch("opencompany.events.bus.get_redis", side_effect=tracked_get),
        patch("opencompany.events.bus._ensure_consumer_group", new_callable=AsyncMock),
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        pytest.raises(asyncio.CancelledError),
    ):
        await bus.subscribe(callback)

    # Should have slept during backoff
    mock_sleep.assert_awaited()
