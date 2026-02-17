"""Tests for the event bus serialization and publish/subscribe logic."""

import json
from unittest.mock import AsyncMock, patch

from opencompany.events.bus import publish


async def test_publish_serializes_and_sends():
    """publish() serializes event data as JSON and publishes to the Redis stream."""
    mock_redis = AsyncMock()

    with patch("opencompany.events.bus.get_redis", return_value=mock_redis):
        await publish("ticket.created", {"id": 1, "title": "Fix bug"})

    mock_redis.xadd.assert_awaited_once()
    stream_key, fields = mock_redis.xadd.call_args[0]
    assert stream_key == "opencompany:events"

    parsed = json.loads(fields["payload"])
    assert parsed["type"] == "ticket.created"
    assert parsed["data"]["id"] == 1
    assert parsed["data"]["title"] == "Fix bug"


async def test_publish_different_event_types():
    """Different event types are correctly encoded."""
    mock_redis = AsyncMock()

    with patch("opencompany.events.bus.get_redis", return_value=mock_redis):
        await publish("persona.hired", {"persona_id": "dev-1"})

    stream_key, fields = mock_redis.xadd.call_args[0]
    payload = json.loads(fields["payload"])
    assert payload["type"] == "persona.hired"
    assert payload["data"]["persona_id"] == "dev-1"
