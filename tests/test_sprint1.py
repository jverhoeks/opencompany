"""Tests for Sprint 1 features: per-task budget, claim_next, capacity hiring, stale expiry."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from opencompany.company.personas import _hire_persona, capacity_ratio
from opencompany.company.taskboard import claim_next
from opencompany.models.db import Persona, Ticket


@pytest.fixture
async def factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# P1: Per-task token budget
# ---------------------------------------------------------------------------
class TestPerTaskBudget:
    async def test_ticket_has_budget_tokens_field(self, factory):
        """Ticket model has budget_tokens with default 4000."""
        async with factory() as session:
            ticket = Ticket(title="Test", tags=["x"])
            session.add(ticket)
            await session.commit()
            await session.refresh(ticket)
            assert ticket.budget_tokens == 4000

    async def test_check_task_budget_requeues_exhausted(self, factory):
        """Ticket with exhausted budget is requeued to open."""
        async with factory() as session:
            session.add(Persona(id="dev", name="Dev", role="Dev", type="solver", backstory="x"))
            ticket = Ticket(
                title="Over budget",
                tags=["x"],
                budget_tokens=1000,
                tokens_in=900,
                tokens_out=200,  # 1100 > 1000, remaining < 200
                status="assigned",
                assigned_to="dev",
            )
            session.add(ticket)
            await session.commit()
            await session.refresh(ticket)
            tid = ticket.id

        with (
            patch("opencompany.company.engine.async_session", factory),
            patch("opencompany.events.bus.get_redis", new_callable=AsyncMock),
        ):
            from opencompany.company.engine import _check_task_budget

            result = await _check_task_budget(tid, "dev")

        assert result is False

        async with factory() as session:
            ticket = await session.get(Ticket, tid)
            assert ticket.status == "open"
            assert ticket.assigned_to is None

    async def test_check_task_budget_allows_with_remaining(self, factory):
        """Ticket with sufficient budget remaining proceeds."""
        async with factory() as session:
            ticket = Ticket(
                title="Has budget",
                tags=["x"],
                budget_tokens=4000,
                tokens_in=100,
                tokens_out=50,
            )
            session.add(ticket)
            await session.commit()
            await session.refresh(ticket)
            tid = ticket.id

        with patch("opencompany.company.engine.async_session", factory):
            from opencompany.company.engine import _check_task_budget

            result = await _check_task_budget(tid, "dev")

        assert result is True

    async def test_check_task_budget_unlimited_when_zero(self, factory):
        """budget_tokens=0 means unlimited."""
        async with factory() as session:
            ticket = Ticket(
                title="Unlimited",
                tags=["x"],
                budget_tokens=0,
                tokens_in=999999,
                tokens_out=999999,
            )
            session.add(ticket)
            await session.commit()
            await session.refresh(ticket)
            tid = ticket.id

        with patch("opencompany.company.engine.async_session", factory):
            from opencompany.company.engine import _check_task_budget

            result = await _check_task_budget(tid, "dev")

        assert result is True


# ---------------------------------------------------------------------------
# P2: Pull-based claim_next
# ---------------------------------------------------------------------------
class TestClaimNext:
    async def test_claim_next_claims_best_match(self, factory):
        """claim_next claims the ticket that best matches persona tags."""
        async with factory() as session:
            session.add(
                Persona(
                    id="py-dev",
                    name="Python Dev",
                    role="Dev",
                    type="solver",
                    picks_up=["backend", "python"],
                    backstory="x",
                )
            )
            session.add(Ticket(title="Frontend task", tags=["frontend"], status="open"))
            t2 = Ticket(title="Backend task", tags=["backend", "python"], status="open")
            session.add(t2)
            await session.commit()
            await session.refresh(t2)
            backend_id = t2.id

        with patch("opencompany.company.taskboard.async_session", factory):
            result = await claim_next("py-dev")

        assert result is not None
        assert result["id"] == backend_id
        assert result["title"] == "Backend task"

        async with factory() as session:
            ticket = await session.get(Ticket, backend_id)
            assert ticket.status == "assigned"
            assert ticket.assigned_to == "py-dev"

    async def test_claim_next_returns_none_when_no_tickets(self, factory):
        """claim_next returns None when no open tickets exist."""
        async with factory() as session:
            session.add(
                Persona(
                    id="dev",
                    name="Dev",
                    role="Dev",
                    type="solver",
                    picks_up=["backend"],
                    backstory="x",
                )
            )
            await session.commit()

        with patch("opencompany.company.taskboard.async_session", factory):
            result = await claim_next("dev")

        assert result is None

    async def test_claim_next_returns_none_for_inactive_persona(self, factory):
        """claim_next returns None for fired personas."""
        async with factory() as session:
            session.add(
                Persona(
                    id="fired",
                    name="Fired",
                    role="Dev",
                    type="solver",
                    status="fired",
                    picks_up=["backend"],
                    backstory="x",
                )
            )
            session.add(Ticket(title="Task", tags=["backend"], status="open"))
            await session.commit()

        with patch("opencompany.company.taskboard.async_session", factory):
            result = await claim_next("fired")

        assert result is None

    async def test_claim_next_skips_assigned_tickets(self, factory):
        """claim_next only considers open unassigned tickets."""
        async with factory() as session:
            session.add(
                Persona(
                    id="dev",
                    name="Dev",
                    role="Dev",
                    type="solver",
                    picks_up=["backend"],
                    backstory="x",
                )
            )
            session.add(
                Ticket(
                    title="Assigned",
                    tags=["backend"],
                    status="assigned",
                    assigned_to="other",
                )
            )
            await session.commit()

        with patch("opencompany.company.taskboard.async_session", factory):
            result = await claim_next("dev")

        assert result is None


# ---------------------------------------------------------------------------
# P3: Capacity-aware hiring
# ---------------------------------------------------------------------------
class TestCapacityHiring:
    async def test_capacity_ratio_no_solvers(self, factory):
        """No active solvers returns infinity."""
        with patch("opencompany.company.personas.async_session", factory):
            ratio = await capacity_ratio()
        assert ratio == float("inf")

    async def test_capacity_ratio_balanced(self, factory):
        """3 open tickets / 2 solvers = 1.5."""
        async with factory() as session:
            for i in range(2):
                session.add(
                    Persona(
                        id=f"solver-{i}",
                        name=f"Solver {i}",
                        role="Dev",
                        type="solver",
                        backstory="x",
                    )
                )
            for i in range(3):
                session.add(Ticket(title=f"Task {i}", tags=["x"], status="open"))
            await session.commit()

        with patch("opencompany.company.personas.async_session", factory):
            ratio = await capacity_ratio()
        assert ratio == 1.5

    async def test_capacity_ratio_counts_assigned_as_pending(self, factory):
        """Assigned (but not yet started) tickets count as pending demand.

        Counting only ``open`` undercounts demand: a team with every ticket
        pushed out but sitting in ``assigned`` state (worker busy, spawn
        dropped by the per-persona semaphore) looked idle to the old ratio.
        """
        async with factory() as session:
            session.add(
                Persona(
                    id="solver-0",
                    name="Solver 0",
                    role="Dev",
                    type="solver",
                    backstory="x",
                )
            )
            session.add(Ticket(title="Open", tags=["x"], status="open"))
            session.add(
                Ticket(
                    title="Assigned",
                    tags=["x"],
                    status="assigned",
                    assigned_to="solver-0",
                )
            )
            # in_progress does NOT count — it's active capacity being used.
            session.add(
                Ticket(
                    title="In Progress",
                    tags=["x"],
                    status="in_progress",
                    assigned_to="solver-0",
                )
            )
            await session.commit()

        with patch("opencompany.company.personas.async_session", factory):
            ratio = await capacity_ratio()
        # 1 open + 1 assigned = 2 pending; 1 solver → 2.0
        assert ratio == 2.0

    async def test_hire_rejected_when_capacity_sufficient(self, factory):
        """Hiring is rejected when capacity ratio < threshold."""
        async with factory() as session:
            # 2 solvers, 1 open ticket → ratio = 0.5
            for i in range(2):
                session.add(
                    Persona(
                        id=f"s-{i}",
                        name=f"S{i}",
                        role="Dev",
                        type="solver",
                        backstory="x",
                    )
                )
            session.add(Ticket(title="T", tags=["x"], status="open"))
            await session.commit()

        with (
            patch("opencompany.company.personas.async_session", factory),
            patch("opencompany.company.personas.os.makedirs"),
            patch("opencompany.company.personas._append_to_company_yaml"),
        ):
            result = await _hire_persona(
                persona_id="new",
                name="New",
                role="Dev",
                persona_type="solver",
                skills=[],
                backstory="x",
            )

        assert "Hiring rejected" in result
        assert "sufficient capacity" in result

    async def test_hire_allowed_when_understaffed(self, factory):
        """Hiring succeeds when capacity ratio >= threshold."""
        async with factory() as session:
            # 1 solver, 3 open tickets → ratio = 3.0
            session.add(
                Persona(
                    id="solo",
                    name="Solo",
                    role="Dev",
                    type="solver",
                    backstory="x",
                )
            )
            for i in range(3):
                session.add(Ticket(title=f"T{i}", tags=["x"], status="open"))
            await session.commit()

        with (
            patch("opencompany.company.personas.async_session", factory),
            patch("opencompany.company.personas.os.makedirs"),
            patch("opencompany.company.personas._append_to_company_yaml"),
            patch(
                "opencompany.company.config.load_company_config",
                side_effect=Exception("no config"),
            ),
        ):
            result = await _hire_persona(
                persona_id="new-dev",
                name="New Dev",
                role="Dev",
                persona_type="solver",
                skills=["python"],
                backstory="x",
            )

        assert "Hired New Dev" in result

    async def test_hire_rejected_at_team_cap(self, factory):
        """Hiring rejected when team size reaches MAX_TEAM_SIZE."""
        async with factory() as session:
            # Create 12 active personas (default cap)
            for i in range(12):
                session.add(
                    Persona(
                        id=f"p-{i}",
                        name=f"P{i}",
                        role=f"Role{i}",
                        type="solver",
                        backstory="x",
                    )
                )
            # Enough open tickets to pass capacity check
            for i in range(20):
                session.add(Ticket(title=f"T{i}", tags=["x"], status="open"))
            await session.commit()

        with (
            patch("opencompany.company.personas.async_session", factory),
            patch("opencompany.company.personas.os.makedirs"),
            patch("opencompany.company.personas._append_to_company_yaml"),
        ):
            result = await _hire_persona(
                persona_id="overflow",
                name="Overflow",
                role="Dev",
                persona_type="solver",
                skills=[],
                backstory="x",
            )

        assert "Error" in result
        assert "12" in result


# ---------------------------------------------------------------------------
# P4: Stale assignment expiry
# ---------------------------------------------------------------------------
class TestStaleAssignmentExpiry:
    async def test_expires_stale_tickets(self, factory):
        """Tickets in_progress for >10 min are reset to open."""
        stale_time = datetime.now(UTC) - timedelta(minutes=15)
        async with factory() as session:
            session.add(Persona(id="dev", name="Dev", role="Dev", type="solver", backstory="x"))
            ticket = Ticket(
                title="Stale task",
                tags=["x"],
                status="in_progress",
                assigned_to="dev",
            )
            session.add(ticket)
            await session.commit()
            await session.refresh(ticket)
            tid = ticket.id

            # Manually set updated_at to 15 minutes ago
            ticket.updated_at = stale_time
            await session.commit()

        with (
            patch("opencompany.models.engine.async_session", factory),
            patch("opencompany.events.bus.get_redis", new_callable=AsyncMock),
        ):
            from opencompany.company.scheduler import _expire_stale_assignments_job

            await _expire_stale_assignments_job()

        async with factory() as session:
            ticket = await session.get(Ticket, tid)
            assert ticket.status == "open"
            assert ticket.assigned_to is None

    async def test_ignores_recent_tickets(self, factory):
        """Recent in_progress tickets are not expired."""
        async with factory() as session:
            session.add(Persona(id="dev", name="Dev", role="Dev", type="solver", backstory="x"))
            ticket = Ticket(
                title="Fresh task",
                tags=["x"],
                status="in_progress",
                assigned_to="dev",
            )
            session.add(ticket)
            await session.commit()
            await session.refresh(ticket)
            tid = ticket.id

        with (
            patch("opencompany.models.engine.async_session", factory),
            patch("opencompany.events.bus.get_redis", new_callable=AsyncMock),
        ):
            from opencompany.company.scheduler import _expire_stale_assignments_job

            await _expire_stale_assignments_job()

        async with factory() as session:
            ticket = await session.get(Ticket, tid)
            assert ticket.status == "in_progress"
            assert ticket.assigned_to == "dev"

    async def test_ignores_open_tickets(self, factory):
        """Open tickets are not touched by expiry."""
        stale_time = datetime.now(UTC) - timedelta(minutes=15)
        async with factory() as session:
            ticket = Ticket(title="Open task", tags=["x"], status="open")
            session.add(ticket)
            await session.commit()
            await session.refresh(ticket)
            tid = ticket.id

            ticket.updated_at = stale_time
            await session.commit()

        with (
            patch("opencompany.models.engine.async_session", factory),
            patch("opencompany.events.bus.get_redis", new_callable=AsyncMock),
        ):
            from opencompany.company.scheduler import _expire_stale_assignments_job

            await _expire_stale_assignments_job()

        async with factory() as session:
            ticket = await session.get(Ticket, tid)
            assert ticket.status == "open"

    async def test_expires_stale_assigned_tickets(self, factory):
        """Assigned (but never started) tickets are reclaimed after the cutoff.

        Regression guard: when ``_spawn_persona_task`` is dropped by the
        per-persona semaphore (worker busy), the ticket sits in ``assigned``
        status forever. The old stale-reclaim only targeted ``in_progress``
        and missed this case, causing tickets to leak indefinitely.
        """
        stale_time = datetime.now(UTC) - timedelta(minutes=15)
        async with factory() as session:
            session.add(Persona(id="dev", name="Dev", role="Dev", type="solver", backstory="x"))
            ticket = Ticket(
                title="Assigned but never started",
                tags=["x"],
                status="assigned",
                assigned_to="dev",
            )
            session.add(ticket)
            await session.commit()
            await session.refresh(ticket)
            tid = ticket.id

            ticket.updated_at = stale_time
            await session.commit()

        with (
            patch("opencompany.models.engine.async_session", factory),
            patch("opencompany.events.bus.get_redis", new_callable=AsyncMock),
        ):
            from opencompany.company.scheduler import _expire_stale_assignments_job

            await _expire_stale_assignments_job()

        async with factory() as session:
            ticket = await session.get(Ticket, tid)
            assert ticket.status == "open"
            assert ticket.assigned_to is None
