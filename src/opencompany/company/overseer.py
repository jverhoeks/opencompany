"""Overseer message storage and relay."""

import logging
from datetime import UTC, datetime

from sqlalchemy import select

from opencompany.models.db import OverseerMessage
from opencompany.models.engine import async_session

logger = logging.getLogger(__name__)


async def store_message(persona_id: str, message: str) -> int:
    """Store a message from a persona to the overseer. Returns message ID."""
    async with async_session() as session:
        msg = OverseerMessage(persona_id=persona_id, message=message)
        session.add(msg)
        await session.commit()
        await session.refresh(msg)
        logger.info("Overseer message #%d from %s stored", msg.id, persona_id)
        return msg.id


async def reply_to_message(message_id: int, reply: str) -> OverseerMessage | None:
    """Store overseer's reply to a persona message."""
    async with async_session() as session:
        msg = await session.get(OverseerMessage, message_id)
        if not msg:
            return None
        msg.reply = reply
        msg.replied_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(msg)
        logger.info("Overseer replied to message #%d", message_id)
        return msg


async def list_messages(
    pending_only: bool = False,
) -> list[dict]:
    """List overseer messages, optionally only those without replies."""
    async with async_session() as session:
        q = select(OverseerMessage).order_by(OverseerMessage.created_at.desc()).limit(100)
        if pending_only:
            q = q.where(OverseerMessage.reply.is_(None))
        result = await session.execute(q)
        return [
            {
                "id": m.id,
                "persona_id": m.persona_id,
                "message": m.message,
                "reply": m.reply,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "replied_at": m.replied_at.isoformat() if m.replied_at else None,
            }
            for m in result.scalars().all()
        ]
