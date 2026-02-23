import logging

from strands import tool

logger = logging.getLogger(__name__)


@tool
def contact_overseer(message: str, persona_id: str) -> str:
    """Send a message to the human overseer for help, escalation, or approval.

    Use this when you're blocked, need human input, or want to escalate an issue.

    Args:
        message: The message to send to the overseer
        persona_id: Your persona ID (the sender)
    """
    from opencompany.company.overseer import store_message
    from opencompany.utils import _run_async

    msg_id = _run_async(store_message(persona_id=persona_id, message=message))
    logger.info("[%s] contact_overseer: %.80s", persona_id, message)
    return f"Message #{msg_id} sent to overseer. They will reply when available."
