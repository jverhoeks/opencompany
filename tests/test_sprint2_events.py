"""Tests for Sprint 2: event-driven scheduler (P0)."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from opencompany.models.db import Persona


@pytest.fixture
async def factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


async def test_handle_event_dispatches_persona_idle(db_engine):
    """handle_event routes persona.idle to _on_persona_idle."""
    with patch("opencompany.company.engine._on_persona_idle", new_callable=AsyncMock) as mock:
        from opencompany.company.engine import handle_event

        await handle_event("persona.idle", {"persona_id": "dev-1"})
        mock.assert_awaited_once_with("dev-1")


async def test_handle_event_handles_persona_blocked():
    """handle_event logs persona.blocked without error."""
    from opencompany.company.engine import handle_event

    # Should not raise
    await handle_event("persona.blocked", {"persona_id": "dev-1", "reason": "budget"})


async def test_spawn_publishes_idle_on_success(db_engine):
    """_spawn_persona_task publishes persona.idle when task completes."""
    import asyncio

    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="pub-dev",
                name="Pub Dev",
                role="Dev",
                type="solver",
                skills=["python"],
                backstory="Test.",
                activity_state="idle",
                daily_token_budget=100000,
            )
        )
        await session.commit()

    from unittest.mock import MagicMock

    mock_result = MagicMock()
    mock_result.input_tokens = 100
    mock_result.output_tokens = 50

    published_events = []
    original_publish = AsyncMock(side_effect=lambda t, d: published_events.append((t, d)))

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch(
            "opencompany.company.engine.run_persona",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
        patch("opencompany.company.budget.async_session", factory),
        patch("opencompany.company.engine.publish", original_publish),
    ):
        from opencompany.company.engine import _spawn_persona_task

        async with factory() as session:
            persona = await session.get(Persona, "pub-dev")

        _spawn_persona_task(persona, "Do work", "test-pub")
        await asyncio.sleep(0.5)

    idle_events = [(t, d) for t, d in published_events if t == "persona.idle"]
    assert len(idle_events) == 1
    assert idle_events[0][1]["persona_id"] == "pub-dev"


async def test_spawn_publishes_blocked_on_error(db_engine):
    """_spawn_persona_task publishes persona.blocked when task fails."""
    import asyncio

    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="err-dev",
                name="Error Dev",
                role="Dev",
                type="solver",
                skills=["python"],
                backstory="Will error.",
                activity_state="idle",
                daily_token_budget=100000,
            )
        )
        await session.commit()

    published_events = []
    original_publish = AsyncMock(side_effect=lambda t, d: published_events.append((t, d)))

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch(
            "opencompany.company.engine.run_persona",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM down"),
        ),
        patch("opencompany.company.budget.async_session", factory),
        patch("opencompany.company.engine.publish", original_publish),
    ):
        from opencompany.company.engine import _spawn_persona_task

        async with factory() as session:
            persona = await session.get(Persona, "err-dev")

        _spawn_persona_task(persona, "Do work", "test-err")
        await asyncio.sleep(0.5)

    blocked_events = [(t, d) for t, d in published_events if t == "persona.blocked"]
    assert len(blocked_events) == 1
    assert blocked_events[0][1]["persona_id"] == "err-dev"
    assert blocked_events[0][1]["reason"] == "task_error"


async def test_spawn_publishes_blocked_on_budget_exhausted(db_engine):
    """_spawn_persona_task publishes persona.blocked when over daily budget."""
    import asyncio
    from datetime import UTC, datetime

    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="broke-dev",
                name="Broke Dev",
                role="Dev",
                type="solver",
                skills=["python"],
                backstory="No budget.",
                activity_state="idle",
                daily_token_budget=100,
                tokens_used_today=200,  # over budget
                budget_reset_at=datetime.now(UTC),  # reset today so it won't auto-reset
            )
        )
        await session.commit()

    published_events = []
    mock_publish = AsyncMock(side_effect=lambda t, d: published_events.append((t, d)))

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.budget.async_session", factory),
        patch("opencompany.company.engine.publish", mock_publish),
    ):
        from opencompany.company.engine import _spawn_persona_task

        async with factory() as session:
            persona = await session.get(Persona, "broke-dev")

        _spawn_persona_task(persona, "Do work", "test-broke")
        await asyncio.sleep(0.5)

    blocked_events = [(t, d) for t, d in published_events if t == "persona.blocked"]
    assert len(blocked_events) == 1
    assert blocked_events[0][1]["reason"] == "daily_budget_exhausted"
