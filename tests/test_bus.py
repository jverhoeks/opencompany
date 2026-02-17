"""Tests for the event bus serialization and publish/subscribe logic."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from opencompany.events.bus import publish, subscribe


async def test_publish_serializes_and_sends():
    """publish() serializes event data as JSON and publishes to the Redis channel."""
    mock_redis = AsyncMock()

    with patch("opencompany.events.bus.get_redis", return_value=mock_redis):
        await publish("ticket.created", {"id": 1, "title": "Fix bug"})

    mock_redis.publish.assert_awaited_once()
    channel, payload = mock_redis.publish.call_args[0]
    assert channel == "opencompany:events"

    parsed = json.loads(payload)
    assert parsed["type"] == "ticket.created"
    assert parsed["data"]["id"] == 1
    assert parsed["data"]["title"] == "Fix bug"


async def test_publish_different_event_types():
    """Different event types are correctly encoded."""
    mock_redis = AsyncMock()

    with patch("opencompany.events.bus.get_redis", return_value=mock_redis):
        await publish("persona.hired", {"persona_id": "dev-1"})

    payload = json.loads(mock_redis.publish.call_args[0][1])
    assert payload["type"] == "persona.hired"
    assert payload["data"]["persona_id"] == "dev-1"


async def test_subscribe_dispatches_messages():
    """subscribe() parses incoming messages and calls the callback."""
    callback = AsyncMock()

    event_payload = json.dumps({"type": "ticket.created", "data": {"id": 42}})
    messages = [
        {"type": "subscribe", "data": None},  # initial subscription confirmation
        {"type": "message", "data": event_payload},
    ]

    mock_pubsub = AsyncMock()
    mock_pubsub.listen = lambda: _async_iter(messages)
    mock_pubsub.subscribe = AsyncMock()

    mock_redis = AsyncMock()
    # pubsub() is a sync method on the redis client, returns the pubsub object directly
    mock_redis.pubsub = MagicMock(return_value=mock_pubsub)

    with patch("opencompany.events.bus.get_redis", return_value=mock_redis):
        await subscribe(callback)

    callback.assert_awaited_once_with("ticket.created", {"id": 42})


async def _async_iter(items):
    """Helper to create an async iterator from a list."""
    for item in items:
        yield item
