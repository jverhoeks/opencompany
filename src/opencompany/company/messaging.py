"""Inter-persona messaging: trigger a target persona to process a message."""

import logging

from opencompany.models.db import Persona
from opencompany.models.engine import async_session

logger = logging.getLogger(__name__)


async def deliver_message(from_persona_id: str, to_persona_id: str, message: str) -> str:
    """Deliver a message from one persona to another, triggering the target to process it."""
    async with async_session() as session:
        sender = await session.get(Persona, from_persona_id)
        recipient = await session.get(Persona, to_persona_id)

        if not sender:
            return f"Error: sender '{from_persona_id}' not found"
        if not recipient:
            return f"Error: recipient '{to_persona_id}' not found"
        if recipient.status != "active":
            return f"Error: recipient '{to_persona_id}' is {recipient.status}"

    # Import here to avoid circular imports
    from opencompany.company.engine import _spawn_persona_task

    task = (
        f"Message from {sender.name} ({sender.role}):\n\n"
        f"{message}\n\n"
        "Process this message and take appropriate action."
    )
    _spawn_persona_task(recipient, task, f"msg-{from_persona_id}-to-{to_persona_id}")

    logger.info("Delivered message from %s to %s", from_persona_id, to_persona_id)
    return f"Message delivered to {recipient.name} ({to_persona_id})"
