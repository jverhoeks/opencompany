"""Tests for opencompany.company.messaging — inter-persona message delivery."""

from unittest.mock import patch

import pytest

from opencompany.models.db import Persona

# ---------------------------------------------------------------------------
# deliver_message
# ---------------------------------------------------------------------------


@pytest.fixture
async def messaging_session(db_engine):
    """Seed two personas and return the patched session factory."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="ceo",
                name="Morgan",
                role="CEO",
                type="manager",
                skills=["strategy"],
                backstory="The boss.",
                status="active",
            )
        )
        session.add(
            Persona(
                id="dev",
                name="Jamie",
                role="Dev",
                type="solver",
                skills=["python"],
                backstory="A dev.",
                status="active",
            )
        )
        session.add(
            Persona(
                id="fired-dev",
                name="Old Dev",
                role="Dev",
                type="solver",
                skills=["python"],
                backstory="Fired.",
                status="fired",
            )
        )
        await session.commit()

    return factory


async def test_deliver_message_success(messaging_session):
    """Message is delivered and _spawn_persona_task is called."""
    with (
        patch("opencompany.company.messaging.async_session", messaging_session),
        patch("opencompany.company.engine._spawn_persona_task") as mock_spawn,
    ):
        from opencompany.company.messaging import deliver_message

        result = await deliver_message("ceo", "dev", "Please fix the login bug")

    assert "delivered" in result.lower()
    assert "Jamie" in result
    mock_spawn.assert_called_once()
    call_args = mock_spawn.call_args[0]
    assert call_args[0].id == "dev"
    assert "Morgan" in call_args[1]
    assert "Please fix the login bug" in call_args[1]


async def test_deliver_message_sender_not_found(messaging_session):
    """Returns error when sender does not exist."""
    with patch("opencompany.company.messaging.async_session", messaging_session):
        from opencompany.company.messaging import deliver_message

        result = await deliver_message("ghost", "dev", "hi")

    assert "error" in result.lower()
    assert "ghost" in result


async def test_deliver_message_recipient_not_found(messaging_session):
    """Returns error when recipient does not exist."""
    with patch("opencompany.company.messaging.async_session", messaging_session):
        from opencompany.company.messaging import deliver_message

        result = await deliver_message("ceo", "nobody", "hi")

    assert "error" in result.lower()
    assert "nobody" in result


async def test_deliver_message_recipient_not_active(messaging_session):
    """Returns error when recipient is not active (e.g. fired)."""
    with patch("opencompany.company.messaging.async_session", messaging_session):
        from opencompany.company.messaging import deliver_message

        result = await deliver_message("ceo", "fired-dev", "hi")

    assert "error" in result.lower()
    assert "fired" in result
