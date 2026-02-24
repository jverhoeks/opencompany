"""Tests for opencompany.company.scheduler — sweep, CEO kickoff, and start_scheduler."""

from unittest.mock import AsyncMock, patch

from opencompany.models.db import Persona

# ---------------------------------------------------------------------------
# _sweep_job
# ---------------------------------------------------------------------------


async def test_sweep_job_calls_sweep(db_engine):
    """_sweep_job calls sweep_unassigned_tickets."""
    mock_sweep = AsyncMock(return_value=2)

    with patch(
        "opencompany.company.engine.sweep_unassigned_tickets",
        mock_sweep,
    ):
        from opencompany.company.scheduler import _sweep_job

        await _sweep_job()

    mock_sweep.assert_awaited_once()


async def test_sweep_job_handles_exception():
    """_sweep_job logs but does not raise on failure."""
    mock_sweep = AsyncMock(side_effect=RuntimeError("DB down"))

    with patch(
        "opencompany.company.engine.sweep_unassigned_tickets",
        mock_sweep,
    ):
        from opencompany.company.scheduler import _sweep_job

        # Should not raise
        await _sweep_job()


# ---------------------------------------------------------------------------
# _ceo_kickoff_job
# ---------------------------------------------------------------------------


async def test_ceo_kickoff_triggers_ceo(db_engine):
    """CEO kickoff spawns a task when CEO is active and idle with budget."""
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
                activity_state="idle",
                daily_token_budget=100000,
            )
        )
        await session.commit()

    with (
        patch("opencompany.models.engine.async_session", factory),
        patch("opencompany.company.budget.async_session", factory),
        patch("opencompany.company.engine._spawn_persona_task") as mock_spawn,
        patch("opencompany.company.engine.set_persona_state", new_callable=AsyncMock),
    ):
        from opencompany.company.scheduler import _ceo_kickoff_job

        await _ceo_kickoff_job()

    mock_spawn.assert_called_once()
    call_args = mock_spawn.call_args[0]
    assert call_args[0].id == "ceo"
    assert "task board" in call_args[1].lower() or "Review" in call_args[1]


async def test_ceo_kickoff_skips_inactive_ceo(db_engine):
    """CEO kickoff skips when CEO is not active."""
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
                backstory="Fired CEO.",
                status="fired",
                activity_state="idle",
            )
        )
        await session.commit()

    with (
        patch("opencompany.models.engine.async_session", factory),
        patch("opencompany.company.engine._spawn_persona_task") as mock_spawn,
    ):
        from opencompany.company.scheduler import _ceo_kickoff_job

        await _ceo_kickoff_job()

    mock_spawn.assert_not_called()


async def test_ceo_kickoff_skips_busy_ceo(db_engine):
    """CEO kickoff skips when CEO is working."""
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
                backstory="Busy CEO.",
                status="active",
                activity_state="working",
            )
        )
        await session.commit()

    with (
        patch("opencompany.models.engine.async_session", factory),
        patch("opencompany.company.engine._spawn_persona_task") as mock_spawn,
    ):
        from opencompany.company.scheduler import _ceo_kickoff_job

        await _ceo_kickoff_job()

    mock_spawn.assert_not_called()


async def test_ceo_kickoff_skips_over_budget(db_engine):
    """CEO kickoff skips when CEO is over budget."""
    from datetime import UTC, datetime

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
                backstory="Over budget CEO.",
                status="active",
                activity_state="idle",
                daily_token_budget=100,
                tokens_used_today=200,
                budget_reset_at=datetime.now(UTC),
            )
        )
        await session.commit()

    with (
        patch("opencompany.models.engine.async_session", factory),
        patch("opencompany.company.budget.async_session", factory),
        patch("opencompany.company.engine._spawn_persona_task") as mock_spawn,
        patch(
            "opencompany.company.engine.set_persona_state",
            new_callable=AsyncMock,
        ) as mock_state,
    ):
        from opencompany.company.scheduler import _ceo_kickoff_job

        await _ceo_kickoff_job()

    mock_spawn.assert_not_called()
    mock_state.assert_awaited_once_with("ceo", "blocked")


async def test_ceo_kickoff_handles_exception():
    """CEO kickoff job logs but does not raise on failure."""
    with patch(
        "opencompany.models.engine.async_session",
        side_effect=RuntimeError("DB down"),
    ):
        from opencompany.company.scheduler import _ceo_kickoff_job

        # Should not raise
        await _ceo_kickoff_job()


async def test_ceo_kickoff_no_ceo(db_engine):
    """CEO kickoff skips when no CEO persona exists."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    with (
        patch("opencompany.models.engine.async_session", factory),
        patch("opencompany.company.engine._spawn_persona_task") as mock_spawn,
    ):
        from opencompany.company.scheduler import _ceo_kickoff_job

        await _ceo_kickoff_job()

    mock_spawn.assert_not_called()


# ---------------------------------------------------------------------------
# start_scheduler
# ---------------------------------------------------------------------------


def test_start_scheduler_adds_sweep_job():
    """start_scheduler always adds the sweep job."""
    from opencompany.company.scheduler import scheduler

    with (
        patch.object(scheduler, "add_job") as mock_add,
        patch.object(scheduler, "start"),
        patch.dict(
            "os.environ",
            {"CEO_KICKOFF_INTERVAL_SECONDS": "0", "HEARTBEAT_INTERVAL_SECONDS": "0"},
        ),
    ):
        from opencompany.company.scheduler import start_scheduler

        start_scheduler()

    # At minimum, sweep job is always added
    calls = mock_add.call_args_list
    job_ids = [c.kwargs.get("id") or c[1].get("id", "") for c in calls]
    assert "sweep_unassigned" in job_ids


def test_start_scheduler_with_ceo_kickoff():
    """start_scheduler adds CEO kickoff when interval > 0."""
    from opencompany.company.scheduler import scheduler

    with (
        patch.object(scheduler, "add_job") as mock_add,
        patch.object(scheduler, "start"),
        patch.dict(
            "os.environ",
            {"CEO_KICKOFF_INTERVAL_SECONDS": "60", "HEARTBEAT_INTERVAL_SECONDS": "0"},
        ),
    ):
        from opencompany.company.scheduler import start_scheduler

        start_scheduler()

    calls = mock_add.call_args_list
    job_ids = [c.kwargs.get("id") or c[1].get("id", "") for c in calls]
    assert "sweep_unassigned" in job_ids
    assert "ceo_kickoff" in job_ids


def test_start_scheduler_with_heartbeat():
    """start_scheduler adds persona heartbeat when interval > 0."""
    from opencompany.company.scheduler import scheduler

    with (
        patch.object(scheduler, "add_job") as mock_add,
        patch.object(scheduler, "start"),
        patch.dict(
            "os.environ",
            {"CEO_KICKOFF_INTERVAL_SECONDS": "0", "HEARTBEAT_INTERVAL_SECONDS": "30"},
        ),
    ):
        from opencompany.company.scheduler import start_scheduler

        start_scheduler()

    calls = mock_add.call_args_list
    job_ids = [c.kwargs.get("id") or c[1].get("id", "") for c in calls]
    assert "sweep_unassigned" in job_ids
    assert "persona_heartbeat" in job_ids


def test_start_scheduler_with_all_jobs():
    """start_scheduler adds all jobs when both intervals > 0."""
    from opencompany.company.scheduler import scheduler

    with (
        patch.object(scheduler, "add_job") as mock_add,
        patch.object(scheduler, "start"),
        patch.dict(
            "os.environ",
            {"CEO_KICKOFF_INTERVAL_SECONDS": "60", "HEARTBEAT_INTERVAL_SECONDS": "30"},
        ),
    ):
        from opencompany.company.scheduler import start_scheduler

        start_scheduler()

    calls = mock_add.call_args_list
    job_ids = [c.kwargs.get("id") or c[1].get("id", "") for c in calls]
    assert "sweep_unassigned" in job_ids
    assert "ceo_kickoff" in job_ids
    assert "persona_heartbeat" in job_ids
