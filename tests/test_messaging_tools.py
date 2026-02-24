"""Coverage tests for agents/tools/messaging.py and agents/tools/overseer.py."""

from unittest.mock import patch


# ---------------------------------------------------------------------------
# send_message tool
# ---------------------------------------------------------------------------
def test_send_message_calls_run_async():
    """send_message tool delegates to _run_async with deliver_message coroutine."""
    with patch(
        "opencompany.utils._run_async",
        return_value="Message delivered to Jamie (dev-1)",
    ) as mock_run:
        from opencompany.agents.tools.messaging import send_message

        result = send_message.__wrapped__(
            to_persona_id="dev-1",
            message="Please review PR #42",
            from_persona_id="ceo",
        )

    assert result == "Message delivered to Jamie (dev-1)"
    mock_run.assert_called_once()


def test_send_message_returns_run_async_result():
    """send_message returns whatever _run_async returns (e.g. error)."""
    with patch(
        "opencompany.utils._run_async",
        return_value="Error: recipient 'nobody' not found",
    ):
        from opencompany.agents.tools.messaging import send_message

        result = send_message.__wrapped__(
            to_persona_id="nobody",
            message="Hello",
            from_persona_id="ceo",
        )

    assert "Error" in result
    assert "nobody" in result


# ---------------------------------------------------------------------------
# contact_overseer tool
# ---------------------------------------------------------------------------
def test_contact_overseer_returns_confirmation():
    """contact_overseer stores message and returns confirmation with ID."""
    with patch(
        "opencompany.utils._run_async",
        return_value=7,
    ):
        from opencompany.agents.tools.overseer import contact_overseer

        result = contact_overseer.__wrapped__(
            message="I need budget approval",
            persona_id="dev-1",
        )

    assert "Message #7" in result
    assert "overseer" in result.lower()


def test_contact_overseer_includes_message_id():
    """contact_overseer includes the stored message ID in its response."""
    with patch(
        "opencompany.utils._run_async",
        return_value=42,
    ):
        from opencompany.agents.tools.overseer import contact_overseer

        result = contact_overseer.__wrapped__(
            message="Escalating blocked ticket",
            persona_id="tech-lead",
        )

    assert "#42" in result
    assert "sent to overseer" in result.lower()
