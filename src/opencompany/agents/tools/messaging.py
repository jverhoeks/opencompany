from strands import tool


@tool
def send_message(to_persona_id: str, message: str, from_persona_id: str) -> str:
    """Send a direct message to another persona, triggering them to process it.

    Use this for inter-persona coordination without creating tickets.

    Args:
        to_persona_id: ID of the persona to message
        message: The message content
        from_persona_id: Your persona ID (the sender)
    """
    from opencompany.company.messaging import deliver_message
    from opencompany.utils import _run_async

    return _run_async(
        deliver_message(
            from_persona_id=from_persona_id,
            to_persona_id=to_persona_id,
            message=message,
        )
    )
