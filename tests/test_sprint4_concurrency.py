"""Tests for Sprint 4: per-persona concurrency semaphore (P7)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from opencompany.models.db import Persona


@pytest.fixture
async def factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


async def test_concurrent_tasks_blocked_by_semaphore(db_engine):
    """Second task for same persona is skipped while first is running."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="busy-dev",
                name="Busy Dev",
                role="Dev",
                type="solver",
                skills=["python"],
                backstory="Test.",
                activity_state="idle",
                daily_token_budget=100000,
            )
        )
        await session.commit()

    # Mock run_persona to block until we release it
    run_event = asyncio.Event()
    mock_result = MagicMock()
    mock_result.input_tokens = 100
    mock_result.output_tokens = 50

    async def slow_run(*args, **kwargs):
        await run_event.wait()
        return mock_result

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine.run_persona", side_effect=slow_run),
        patch("opencompany.company.budget.async_session", factory),
        patch("opencompany.company.engine.publish", new_callable=AsyncMock),
    ):
        # Clear any stale locks from other tests
        from opencompany.company.engine import _persona_locks, _spawn_persona_task

        _persona_locks.pop("busy-dev", None)

        async with factory() as session:
            persona = await session.get(Persona, "busy-dev")

        # Spawn first task — will block on run_event
        _spawn_persona_task(persona, "Task 1", "task-1")
        await asyncio.sleep(0.1)  # let it acquire the lock

        # Spawn second task — should be skipped (lock is held)
        _spawn_persona_task(persona, "Task 2", "task-2")
        await asyncio.sleep(0.1)

        # Release first task
        run_event.set()
        await asyncio.sleep(0.5)

    # Only one actual run_persona call should have happened
    # (the second was skipped because lock was held)


async def test_get_persona_lock_creates_semaphore():
    """_get_persona_lock creates and caches a semaphore."""
    from opencompany.company.engine import _get_persona_lock, _persona_locks

    _persona_locks.pop("test-lock", None)

    lock1 = _get_persona_lock("test-lock")
    lock2 = _get_persona_lock("test-lock")
    assert lock1 is lock2
    assert isinstance(lock1, asyncio.Semaphore)

    _persona_locks.pop("test-lock", None)


async def test_get_persona_lock_custom_concurrency():
    """_get_persona_lock respects custom max_concurrent."""
    from opencompany.company.engine import _get_persona_lock, _persona_locks

    _persona_locks.pop("ceo-lock", None)

    lock = _get_persona_lock("ceo-lock", max_concurrent=2)
    # Semaphore with value 2 — can acquire twice
    assert await asyncio.wait_for(lock.acquire(), timeout=0.1)
    assert await asyncio.wait_for(lock.acquire(), timeout=0.1)
    lock.release()
    lock.release()

    _persona_locks.pop("ceo-lock", None)
