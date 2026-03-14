"""Tests for Sprint 11: S4 Redis session manager for persona memory."""

import json
from unittest.mock import AsyncMock, patch

from opencompany.agents.session import RedisSessionManager, get_session_manager


class TestRedisSessionManager:
    async def test_save_and_load(self):
        """Save messages, then load them back."""
        mock_redis = AsyncMock()
        stored = {}

        async def mock_set(key, value, ex=None):
            stored[key] = value

        async def mock_get(key):
            return stored.get(key)

        mock_redis.set = mock_set
        mock_redis.get = mock_get

        with patch(
            "opencompany.events.bus.get_redis",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            mgr = RedisSessionManager(ttl=3600)
            messages = [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
            ]

            await mgr.save("dev-1", messages)
            loaded = await mgr.load("dev-1")

        assert len(loaded) == 2
        assert loaded[0]["content"] == "Hello"
        assert loaded[1]["content"] == "Hi there!"

    async def test_load_empty_when_no_session(self):
        """Load returns empty list when no session exists."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with patch(
            "opencompany.events.bus.get_redis",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            mgr = RedisSessionManager()
            loaded = await mgr.load("nonexistent")

        assert loaded == []

    async def test_save_truncates_to_50(self):
        """Save keeps only the most recent 50 messages."""
        mock_redis = AsyncMock()
        saved_data = {}

        async def mock_set(key, value, ex=None):
            saved_data[key] = value

        mock_redis.set = mock_set

        with patch(
            "opencompany.events.bus.get_redis",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            mgr = RedisSessionManager()
            messages = [{"role": "user", "content": f"msg {i}"} for i in range(100)]
            await mgr.save("dev-1", messages)

        stored = json.loads(saved_data["opencompany:session:dev-1"])
        assert len(stored) == 50
        assert stored[0]["content"] == "msg 50"  # kept the last 50

    async def test_clear(self):
        """Clear deletes the session key."""
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock()

        with patch(
            "opencompany.events.bus.get_redis",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            mgr = RedisSessionManager()
            await mgr.clear("dev-1")

        mock_redis.delete.assert_awaited_once_with("opencompany:session:dev-1")

    async def test_load_handles_redis_error(self):
        """Load returns empty list when Redis is unavailable."""
        with patch(
            "opencompany.events.bus.get_redis",
            new_callable=AsyncMock,
            side_effect=ConnectionError("Redis down"),
        ):
            mgr = RedisSessionManager()
            loaded = await mgr.load("dev-1")

        assert loaded == []

    async def test_save_handles_redis_error(self):
        """Save fails silently when Redis is unavailable."""
        with patch(
            "opencompany.events.bus.get_redis",
            new_callable=AsyncMock,
            side_effect=ConnectionError("Redis down"),
        ):
            mgr = RedisSessionManager()
            # Should not raise
            await mgr.save("dev-1", [{"role": "user", "content": "test"}])


class TestGetSessionManager:
    def test_returns_singleton(self):
        from opencompany.agents import session

        session._session_manager = None
        mgr1 = get_session_manager()
        mgr2 = get_session_manager()
        assert mgr1 is mgr2
        session._session_manager = None  # cleanup
