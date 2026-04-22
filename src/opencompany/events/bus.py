"""Event bus backed by Redis Streams for guaranteed delivery."""

import asyncio
import json
import logging
import os
import socket
from collections.abc import Callable

import redis.asyncio as redis

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
STREAM_KEY = "opencompany:events"
GROUP_NAME = "opencompany-workers"
CONSUMER_NAME = os.environ.get("HOSTNAME", socket.gethostname())

# Max deliveries before a stuck message is ACKed and dropped. Prevents a single
# poison-pill event from blocking the stream forever.
MAX_DELIVERY_ATTEMPTS = int(os.environ.get("EVENT_MAX_DELIVERY_ATTEMPTS", "5"))
# How long before idle pending messages are claimed from a dead consumer (ms).
CLAIM_STALE_MS = int(os.environ.get("EVENT_CLAIM_STALE_MS", "60000"))

_pool: redis.ConnectionPool | None = None
_redis: redis.Redis | None = None
_lock = asyncio.Lock()


async def init_redis() -> None:
    """Create the Redis connection pool. Call once at startup."""
    global _pool, _redis
    async with _lock:
        if _pool is not None:
            return
        _pool = redis.ConnectionPool.from_url(REDIS_URL, decode_responses=True)
        _redis = redis.Redis(connection_pool=_pool)
        logger.info("Redis connection pool initialised")


async def close_redis() -> None:
    """Close the Redis connection pool. Call once at shutdown."""
    global _pool, _redis
    async with _lock:
        if _redis is not None:
            await _redis.aclose()
            _redis = None
        if _pool is not None:
            await _pool.aclose()
            _pool = None
        logger.info("Redis connection pool closed")


async def get_redis() -> redis.Redis:
    """Return the shared Redis client, initialising lazily if needed."""
    if _redis is not None:
        return _redis
    await init_redis()
    assert _redis is not None
    return _redis


async def ping() -> bool:
    """Health-check: return True if Redis is reachable."""
    try:
        r = await get_redis()
        return await r.ping()
    except Exception:
        return False


async def _ensure_consumer_group(r: redis.Redis) -> None:
    """Create the consumer group if it does not exist yet."""
    try:
        await r.xgroup_create(STREAM_KEY, GROUP_NAME, id="0", mkstream=True)
        logger.info("Created consumer group %s on %s", GROUP_NAME, STREAM_KEY)
    except redis.ResponseError as exc:
        if "BUSYGROUP" in str(exc):
            pass  # group already exists
        else:
            raise


async def publish(event_type: str, data: dict) -> None:
    """Publish an event to the stream."""
    r = await get_redis()
    payload = json.dumps({"type": event_type, "data": data})
    await r.xadd(STREAM_KEY, {"payload": payload})
    logger.info("Published event %s: %s", event_type, data)


async def _claim_stale_pending(r: redis.Redis) -> list[tuple[str, dict]]:
    """Claim messages from dead consumers (pending > CLAIM_STALE_MS).

    Returns a list of ``(msg_id, fields)`` pairs that this consumer now owns.
    Using XAUTOCLAIM ensures a crashed worker's in-flight work is picked up
    rather than sitting in the Pending Entry List forever.
    """
    try:
        _next, claimed, _deleted = await r.xautoclaim(
            STREAM_KEY,
            GROUP_NAME,
            CONSUMER_NAME,
            min_idle_time=CLAIM_STALE_MS,
            start_id="0-0",
            count=50,
        )
    except Exception:
        logger.exception("xautoclaim failed; skipping reclaim round")
        return []
    return list(claimed or [])


async def _handle_entry(
    r: redis.Redis,
    callback: Callable,
    msg_id: str,
    fields: dict,
) -> None:
    """Decode, dispatch, ACK. Poison-pill entries get ACKed after N attempts."""
    try:
        payload_raw = fields.get("payload") or fields.get(b"payload")
        if payload_raw is None:
            logger.error("Event %s missing payload field, dropping", msg_id)
            await r.xack(STREAM_KEY, GROUP_NAME, msg_id)
            return
        payload = json.loads(payload_raw)
        logger.info("Received event %s: %s", payload.get("type"), payload.get("data"))
        await callback(payload["type"], payload["data"])
        await r.xack(STREAM_KEY, GROUP_NAME, msg_id)
        return
    except Exception:
        logger.exception("Error processing event %s", msg_id)

    # Look up how many times this entry has been delivered. If we've
    # exceeded our budget, ACK and drop — the entry is a poison pill and
    # blocking the stream on it makes every downstream worker stall.
    try:
        pending = await r.xpending_range(STREAM_KEY, GROUP_NAME, min=msg_id, max=msg_id, count=1)
    except Exception:
        pending = []
    attempts = int(pending[0].get("times_delivered", 0)) if pending else 0
    if attempts >= MAX_DELIVERY_ATTEMPTS:
        logger.error(
            "Event %s failed %d times — ACKing to unblock stream (dead-letter)",
            msg_id,
            attempts,
        )
        try:
            await r.xack(STREAM_KEY, GROUP_NAME, msg_id)
        except Exception:
            logger.warning("Dead-letter ACK for %s failed; will retry next cycle", msg_id)


async def subscribe(callback: Callable) -> None:
    """Read events via XREADGROUP and ACK after processing.

    Blocks indefinitely; intended to run as a background task.
    Uses exponential backoff on transient errors, reclaims stale pending
    entries from dead consumers, and drops poison-pill messages after
    ``MAX_DELIVERY_ATTEMPTS`` failed deliveries.
    """
    r = await get_redis()
    await _ensure_consumer_group(r)
    logger.info("Subscribed to event bus via consumer group %s", GROUP_NAME)

    backoff = 0.5
    max_backoff = 30.0
    reclaim_every = 30  # read cycles between XAUTOCLAIM sweeps
    cycles = 0

    while True:
        try:
            # Periodically reclaim entries left pending by a crashed consumer.
            cycles += 1
            if cycles % reclaim_every == 0:
                claimed = await _claim_stale_pending(r)
                for msg_id, fields in claimed:
                    await _handle_entry(r, callback, msg_id, fields)

            messages = await r.xreadgroup(
                GROUP_NAME,
                CONSUMER_NAME,
                {STREAM_KEY: ">"},
                count=10,
                block=5000,
            )
            if not messages:
                backoff = 0.5  # reset on successful (empty) read
                continue

            for _stream, entries in messages:
                for msg_id, fields in entries:
                    await _handle_entry(r, callback, msg_id, fields)

            backoff = 0.5  # reset after successful processing

        except asyncio.CancelledError:
            logger.info("Event subscriber cancelled, shutting down")
            raise
        except Exception:
            logger.exception("Event subscriber error, retrying in %.1fs", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)
            # Re-acquire the client in case of reconnect
            r = await get_redis()
