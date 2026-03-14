"""Redis-backed session manager for persona conversation history.

Stores conversation context per persona in Redis, surviving container
restarts without requiring the custom PersonaMemory table. Works with
the existing Redis sidecar.

Usage in runner.py:
    session_mgr = get_session_manager()
    # Before creating agent: load prior context
    history = await session_mgr.load(persona_id)
    # After agent run: save updated context
    await session_mgr.save(persona_id, messages)
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

_SESSION_TTL = int(os.environ.get("SESSION_TTL_SECONDS", str(86400 * 7)))  # 7 days
_KEY_PREFIX = "opencompany:session:"


class RedisSessionManager:
    """Lightweight session manager using Redis for persona conversation history."""

    def __init__(self, ttl: int = _SESSION_TTL):
        self.ttl = ttl

    def _key(self, persona_id: str) -> str:
        return f"{_KEY_PREFIX}{persona_id}"

    async def load(self, persona_id: str) -> list[dict]:
        """Load conversation history for a persona from Redis.

        Returns a list of message dicts (role, content) or empty list.
        """
        try:
            from opencompany.events.bus import get_redis

            r = await get_redis()
            data = await r.get(self._key(persona_id))
            if data:
                messages = json.loads(data)
                logger.debug(
                    "Loaded %d messages for persona %s",
                    len(messages),
                    persona_id,
                )
                return messages
        except Exception:
            logger.debug("Could not load session for %s", persona_id, exc_info=True)
        return []

    async def save(self, persona_id: str, messages: list[dict]) -> None:
        """Save conversation history for a persona to Redis.

        Truncates to the most recent 50 messages to prevent unbounded growth.
        """
        try:
            from opencompany.events.bus import get_redis

            # Keep only recent messages
            truncated = messages[-50:] if len(messages) > 50 else messages
            r = await get_redis()
            await r.set(
                self._key(persona_id),
                json.dumps(truncated),
                ex=self.ttl,
            )
            logger.debug(
                "Saved %d messages for persona %s (ttl=%ds)",
                len(truncated),
                persona_id,
                self.ttl,
            )
        except Exception:
            logger.debug("Could not save session for %s", persona_id, exc_info=True)

    async def clear(self, persona_id: str) -> None:
        """Clear conversation history for a persona."""
        try:
            from opencompany.events.bus import get_redis

            r = await get_redis()
            await r.delete(self._key(persona_id))
            logger.info("Cleared session for persona %s", persona_id)
        except Exception:
            logger.debug("Could not clear session for %s", persona_id, exc_info=True)


# Module-level singleton
_session_manager: RedisSessionManager | None = None


def get_session_manager() -> RedisSessionManager:
    """Get or create the global session manager."""
    global _session_manager
    if _session_manager is None:
        _session_manager = RedisSessionManager()
    return _session_manager
