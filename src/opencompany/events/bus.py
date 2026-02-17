import json
import logging
import os
from collections.abc import Callable

import redis.asyncio as redis

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

_redis: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis


async def publish(event_type: str, data: dict):
    """Publish an event to the bus."""
    r = await get_redis()
    payload = json.dumps({"type": event_type, "data": data})
    await r.publish("opencompany:events", payload)
    logger.debug("Published event %s", event_type)


async def subscribe(callback: Callable):
    """Subscribe to all events. Calls callback(event_type, data) for each."""
    r = await get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe("opencompany:events")
    logger.info("Subscribed to event bus")

    async for message in pubsub.listen():
        if message["type"] == "message":
            payload = json.loads(message["data"])
            logger.debug("Received event %s", payload["type"])
            await callback(payload["type"], payload["data"])
