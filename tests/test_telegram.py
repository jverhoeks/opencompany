"""Tests for the Telegram channel adapter."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from opencompany.gateway.channels.telegram import (
    _handle_message,
    _handle_start,
    _resolve_persona,
    create_telegram_app,
)


# ---------------------------------------------------------------------------
# Helpers to build fake Telegram objects
# ---------------------------------------------------------------------------
def _make_update(text="hello", chat_type="private", user_id=12345):
    """Build a minimal mock Update with message, chat, and user."""
    update = MagicMock()
    update.message = AsyncMock()
    update.message.text = text
    update.message.reply_text = AsyncMock()
    update.effective_chat = MagicMock()
    update.effective_chat.type = chat_type
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    return update


# ---------------------------------------------------------------------------
# _resolve_persona
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_persona():
    persona = MagicMock()
    persona.id = "ceo"
    persona.name = "Alice CEO"
    return persona


async def test_resolve_persona_found(mock_persona):
    """Returns the default persona when found in DB."""
    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=mock_persona)
    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("opencompany.gateway.channels.telegram.async_session", mock_factory):
        result = await _resolve_persona("telegram", "direct", "12345")

    assert result is mock_persona


async def test_resolve_persona_not_found():
    """Returns None when the default persona is not in DB."""
    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=None)
    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("opencompany.gateway.channels.telegram.async_session", mock_factory):
        result = await _resolve_persona("telegram", "direct", "99")

    assert result is None


# ---------------------------------------------------------------------------
# _handle_start
# ---------------------------------------------------------------------------
async def test_handle_start_sends_welcome():
    """The /start command sends a welcome message."""
    update = _make_update()
    ctx = MagicMock()

    await _handle_start(update, ctx)

    update.message.reply_text.assert_awaited_once()
    call_text = update.message.reply_text.call_args[0][0]
    assert "Welcome" in call_text


async def test_handle_start_exception():
    """Exception in reply_text is swallowed."""
    update = _make_update()
    update.message.reply_text = AsyncMock(side_effect=RuntimeError("send failed"))
    ctx = MagicMock()

    # Should not raise
    await _handle_start(update, ctx)


# ---------------------------------------------------------------------------
# _handle_message
# ---------------------------------------------------------------------------
async def test_handle_message_no_persona():
    """When no persona is resolved, sends 'No persona available.'."""
    update = _make_update(text="test message")
    ctx = MagicMock()

    with patch(
        "opencompany.gateway.channels.telegram._resolve_persona",
        new_callable=AsyncMock,
        return_value=None,
    ):
        await _handle_message(update, ctx)

    # Should have called reply_text with "No persona available."
    calls = update.message.reply_text.await_args_list
    assert any("No persona available" in str(c) for c in calls)


async def test_handle_message_success(mock_persona):
    """Successful message processing sends 'Processing...' then the result."""
    update = _make_update(text="What's the status?")
    ctx = MagicMock()

    mock_result = MagicMock()
    mock_result.text = "Everything is fine."

    with (
        patch(
            "opencompany.gateway.channels.telegram._resolve_persona",
            new_callable=AsyncMock,
            return_value=mock_persona,
        ),
        patch(
            "opencompany.gateway.channels.telegram.run_persona",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_run,
    ):
        await _handle_message(update, ctx)

    # Should have called reply_text at least twice: "Processing..." and result
    assert update.message.reply_text.await_count >= 2
    # Verify run_persona was called with the persona and a wrapped message
    mock_run.assert_awaited_once()
    call_args = mock_run.call_args
    assert call_args[0][0] is mock_persona
    assert "USER MESSAGE" in call_args[0][1]


async def test_handle_message_long_result(mock_persona):
    """Long results are chunked to 4000 char pieces."""
    update = _make_update(text="long response please")
    ctx = MagicMock()

    mock_result = MagicMock()
    mock_result.text = "A" * 8500  # >4000 chars

    with (
        patch(
            "opencompany.gateway.channels.telegram._resolve_persona",
            new_callable=AsyncMock,
            return_value=mock_persona,
        ),
        patch(
            "opencompany.gateway.channels.telegram.run_persona",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
    ):
        await _handle_message(update, ctx)

    # Processing + 3 chunks (8500 / 4000 = 3 chunks)
    assert update.message.reply_text.await_count == 4


async def test_handle_message_result_no_text_attr(mock_persona):
    """Result without .text attribute falls back to str()."""
    update = _make_update(text="hello")
    ctx = MagicMock()

    mock_result = "plain string result"

    with (
        patch(
            "opencompany.gateway.channels.telegram._resolve_persona",
            new_callable=AsyncMock,
            return_value=mock_persona,
        ),
        patch(
            "opencompany.gateway.channels.telegram.run_persona",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
    ):
        await _handle_message(update, ctx)

    calls = update.message.reply_text.await_args_list
    assert any("plain string result" in str(c) for c in calls)


async def test_handle_message_group_chat(mock_persona):
    """Group chats are identified as 'group' chat_type."""
    update = _make_update(text="group msg", chat_type="supergroup")
    ctx = MagicMock()

    mock_result = MagicMock()
    mock_result.text = "Reply from group."

    with (
        patch(
            "opencompany.gateway.channels.telegram._resolve_persona",
            new_callable=AsyncMock,
            return_value=mock_persona,
        ) as mock_resolve,
        patch(
            "opencompany.gateway.channels.telegram.run_persona",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
    ):
        await _handle_message(update, ctx)

    # Verify the chat_type passed to _resolve_persona is "group"
    mock_resolve.assert_awaited_once_with("telegram", "group", str(update.effective_user.id))


async def test_handle_message_exception(mock_persona):
    """Exceptions during run_persona are caught and a sorry message is sent."""
    update = _make_update(text="fail me")
    ctx = MagicMock()

    with (
        patch(
            "opencompany.gateway.channels.telegram._resolve_persona",
            new_callable=AsyncMock,
            return_value=mock_persona,
        ),
        patch(
            "opencompany.gateway.channels.telegram.run_persona",
            new_callable=AsyncMock,
            side_effect=RuntimeError("agent error"),
        ),
    ):
        await _handle_message(update, ctx)

    calls = update.message.reply_text.await_args_list
    assert any("something went wrong" in str(c) for c in calls)


# ---------------------------------------------------------------------------
# create_telegram_app
# ---------------------------------------------------------------------------
def test_create_telegram_app_no_token(monkeypatch):
    """Returns None when TELEGRAM_BOT_TOKEN is not set."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    result = create_telegram_app()
    assert result is None


def test_create_telegram_app_with_token(monkeypatch):
    """Returns an Application when TELEGRAM_BOT_TOKEN is set."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token-123")

    mock_app = MagicMock()
    mock_builder = MagicMock()
    mock_builder.token.return_value = mock_builder
    mock_builder.build.return_value = mock_app

    with patch(
        "opencompany.gateway.channels.telegram.Application.builder",
        return_value=mock_builder,
    ):
        result = create_telegram_app()

    assert result is mock_app
    mock_builder.token.assert_called_once_with("fake-token-123")
    mock_app.add_handler.assert_called()
    assert mock_app.add_handler.call_count == 2  # /start + message handler
