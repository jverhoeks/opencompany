import logging

from strands import tool

logger = logging.getLogger(__name__)


@tool
def contact_overseer(message: str, persona_id: str) -> str:
    """Send a message to the customer (human overseer) for clarification or status updates.

    The overseer is the CUSTOMER — they provide requirements and feedback.
    They do NOT make business decisions; that is the CEO's job.
    Use this only when you need customer input, clarification on requirements,
    or to report progress. Never ask the customer what to do next.

    Args:
        message: The message to send to the customer
        persona_id: Your persona ID (the sender)
    """
    from opencompany.company.overseer import store_message
    from opencompany.utils import _run_async

    msg_id = _run_async(store_message(persona_id=persona_id, message=message))
    logger.info("[%s] contact_overseer: %.80s", persona_id, message)
    return f"Message #{msg_id} sent to overseer. They will reply when available."
