"""Tests for opencompany.company.overseer — overseer message storage and relay."""

from unittest.mock import patch

import pytest

from opencompany.models.db import Persona


@pytest.fixture
async def overseer_session(db_engine):
    """Seed a persona and return the patched session factory."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="dev",
                name="Jamie",
                role="Dev",
                type="solver",
                skills=["python"],
                backstory="A dev.",
            )
        )
        await session.commit()

    return factory


async def test_store_message(overseer_session):
    """store_message persists a message and returns its ID."""
    with patch("opencompany.company.overseer.async_session", overseer_session):
        from opencompany.company.overseer import store_message

        msg_id = await store_message("dev", "I need more resources")

    assert isinstance(msg_id, int)
    assert msg_id > 0


async def test_reply_to_message(overseer_session):
    """reply_to_message updates the message with a reply."""
    with patch("opencompany.company.overseer.async_session", overseer_session):
        from opencompany.company.overseer import reply_to_message, store_message

        msg_id = await store_message("dev", "Need help")
        msg = await reply_to_message(msg_id, "Help is on the way")

    assert msg is not None
    assert msg.reply == "Help is on the way"
    assert msg.replied_at is not None


async def test_reply_to_nonexistent_message(overseer_session):
    """reply_to_message returns None for a non-existent ID."""
    with patch("opencompany.company.overseer.async_session", overseer_session):
        from opencompany.company.overseer import reply_to_message

        result = await reply_to_message(9999, "This should fail")

    assert result is None


async def test_list_messages_all(overseer_session):
    """list_messages returns all stored messages."""
    with patch("opencompany.company.overseer.async_session", overseer_session):
        from opencompany.company.overseer import list_messages, store_message

        await store_message("dev", "First message")
        await store_message("dev", "Second message")

        messages = await list_messages()

    assert len(messages) == 2
    texts = {m["message"] for m in messages}
    assert texts == {"First message", "Second message"}
    # All messages should have correct fields
    for m in messages:
        assert "id" in m
        assert "persona_id" in m
        assert m["persona_id"] == "dev"
        assert "created_at" in m


async def test_list_messages_pending_only(overseer_session):
    """list_messages with pending_only=True returns only unreplied messages."""
    with patch("opencompany.company.overseer.async_session", overseer_session):
        from opencompany.company.overseer import (
            list_messages,
            reply_to_message,
            store_message,
        )

        id1 = await store_message("dev", "Replied message")
        await store_message("dev", "Pending message")

        await reply_to_message(id1, "Done")

        pending = await list_messages(pending_only=True)

    assert len(pending) == 1
    assert pending[0]["message"] == "Pending message"
    assert pending[0]["reply"] is None


async def test_list_messages_empty(overseer_session):
    """list_messages returns empty list when no messages exist."""
    with patch("opencompany.company.overseer.async_session", overseer_session):
        from opencompany.company.overseer import list_messages

        messages = await list_messages()

    assert messages == []
