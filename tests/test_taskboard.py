"""Tests for opencompany.company.taskboard — ticket lifecycle and auto-assignment."""

from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import async_sessionmaker

from opencompany.company.taskboard import find_best_solver
from opencompany.models.db import Persona, Ticket


def test_find_best_solver_matches_skills():
    solvers = [
        {"id": "backend-dev", "skills": ["python", "backend"], "workload": 3},
        {"id": "security-eng", "skills": ["security", "python"], "workload": 1},
    ]
    best = find_best_solver(tags=["security"], solvers=solvers)
    assert best["id"] == "security-eng"


def test_find_best_solver_prefers_lower_workload():
    solvers = [
        {"id": "dev-1", "skills": ["python"], "workload": 5},
        {"id": "dev-2", "skills": ["python"], "workload": 2},
    ]
    best = find_best_solver(tags=["python"], solvers=solvers)
    assert best["id"] == "dev-2"


def test_find_best_solver_no_match_falls_back_to_least_busy():
    solvers = [
        {"id": "dev-1", "skills": ["python"], "workload": 3},
        {"id": "dev-2", "skills": ["java"], "workload": 1},
    ]
    best = find_best_solver(tags=["rust"], solvers=solvers)
    assert best["id"] == "dev-2"  # least busy gets it


def test_find_best_solver_empty_solvers():
    best = find_best_solver(tags=["rust"], solvers=[])
    assert best is None


def test_find_best_solver_multiple_tag_overlap():
    solvers = [
        {"id": "dev-1", "skills": ["python", "security"], "workload": 2},
        {"id": "dev-2", "skills": ["python"], "workload": 1},
    ]
    best = find_best_solver(tags=["python", "security"], solvers=solvers)
    assert best["id"] == "dev-1"  # more skill overlap wins despite higher workload


# ---------------------------------------------------------------------------
# _create_ticket (DB path)
# ---------------------------------------------------------------------------


@patch("opencompany.company.taskboard.publish", new_callable=AsyncMock)
async def test_create_ticket_db(mock_pub, db_engine):
    """_create_ticket inserts a ticket and publishes an event."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="creator",
                name="Creator",
                role="Dev",
                type="solver",
                backstory="Creates tickets.",
            )
        )
        await session.commit()

    with patch("opencompany.company.taskboard.async_session", factory):
        from opencompany.company.taskboard import _create_ticket

        ticket_id = await _create_ticket(
            title="New ticket",
            description="A test ticket",
            priority="high",
            tags=["backend", "api"],
            context={"file": "main.py"},
            created_by="creator",
        )

    assert isinstance(ticket_id, int)
    assert ticket_id > 0

    # Verify persisted
    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        assert ticket is not None
        assert ticket.title == "New ticket"
        assert ticket.priority == "high"
        assert ticket.tags == ["backend", "api"]
        assert ticket.created_by == "creator"

    mock_pub.assert_awaited_once_with("ticket.created", {"ticket_id": ticket_id})


# ---------------------------------------------------------------------------
# _list_tickets (DB path)
# ---------------------------------------------------------------------------


@patch("opencompany.company.taskboard.publish", new_callable=AsyncMock)
async def test_list_tickets_by_status(mock_pub, db_engine):
    """_list_tickets filters by status."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(Ticket(title="Open 1", status="open"))
        session.add(Ticket(title="Open 2", status="open", tags=["backend"]))
        session.add(Ticket(title="Closed 1", status="done"))
        await session.commit()

    with patch("opencompany.company.taskboard.async_session", factory):
        from opencompany.company.taskboard import _list_tickets

        open_tickets = await _list_tickets(status="open", tags=[])
        done_tickets = await _list_tickets(status="done", tags=[])

    assert len(open_tickets) == 2
    assert len(done_tickets) == 1
    assert done_tickets[0]["title"] == "Closed 1"


@patch("opencompany.company.taskboard.publish", new_callable=AsyncMock)
async def test_list_tickets_with_tag_filter(mock_pub, db_engine):
    """_list_tickets filters by tags when provided."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(Ticket(title="Backend", status="open", tags=["backend"]))
        session.add(Ticket(title="Frontend", status="open", tags=["frontend"]))
        session.add(Ticket(title="Both", status="open", tags=["backend", "frontend"]))
        await session.commit()

    with patch("opencompany.company.taskboard.async_session", factory):
        from opencompany.company.taskboard import _list_tickets

        backend_tickets = await _list_tickets(status="open", tags=["backend"])

    assert len(backend_tickets) == 2
    titles = {t["title"] for t in backend_tickets}
    assert titles == {"Backend", "Both"}


# ---------------------------------------------------------------------------
# _update_ticket (DB path)
# ---------------------------------------------------------------------------


async def test_update_ticket_status(db_engine):
    """_update_ticket updates status and creates a work log."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="dev",
                name="Dev",
                role="Dev",
                type="solver",
                backstory="A dev.",
            )
        )
        ticket = Ticket(title="Test ticket", status="open", created_by="dev")
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        ticket_id = ticket.id

    with (
        patch("opencompany.company.taskboard.async_session", factory),
        patch("opencompany.company.taskboard.publish", new_callable=AsyncMock),
    ):
        from opencompany.company.taskboard import _update_ticket

        await _update_ticket(ticket_id=ticket_id, status="in_progress")

    async with factory() as session:
        updated = await session.get(Ticket, ticket_id)
        assert updated.status == "in_progress"


async def test_update_ticket_not_found(db_engine):
    """_update_ticket returns error string for missing ticket."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    with (
        patch("opencompany.company.taskboard.async_session", factory),
        patch("opencompany.company.taskboard.publish", new_callable=AsyncMock),
    ):
        from opencompany.company.taskboard import _update_ticket

        result = await _update_ticket(ticket_id=9999, status="done")

    assert result is not None
    assert "error" in result.lower()


async def test_update_ticket_result(db_engine):
    """_update_ticket stores result text."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="dev",
                name="Dev",
                role="Dev",
                type="solver",
                backstory="A dev.",
            )
        )
        ticket = Ticket(title="Solve bug", status="assigned", created_by="dev")
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        ticket_id = ticket.id

    with (
        patch("opencompany.company.taskboard.async_session", factory),
        patch("opencompany.company.taskboard.publish", new_callable=AsyncMock),
    ):
        from opencompany.company.taskboard import _update_ticket

        await _update_ticket(ticket_id=ticket_id, result="Fixed the bug in auth.py")

    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        assert ticket.result == "Fixed the bug in auth.py"


@patch("opencompany.company.taskboard.publish", new_callable=AsyncMock)
async def test_update_ticket_review_publishes_event(mock_pub, db_engine):
    """_update_ticket publishes ticket.review event when status is 'review'."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="dev",
                name="Dev",
                role="Dev",
                type="solver",
                backstory="A dev.",
            )
        )
        ticket = Ticket(title="Review me", status="in_progress", created_by="dev")
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        ticket_id = ticket.id

    with patch("opencompany.company.taskboard.async_session", factory):
        from opencompany.company.taskboard import _update_ticket

        await _update_ticket(ticket_id=ticket_id, status="review", result="Done")

    mock_pub.assert_awaited_once_with("ticket.review", {"ticket_id": ticket_id})

    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        assert ticket.status == "review"
        assert ticket.result == "Done"
