"""End-to-end tests for the OpenCompany API.

Uses an in-memory SQLite database (no Docker required) and mocks the LLM agent
runner so tests are fast, deterministic, and fully offline.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from opencompany.gateway.api import router
from opencompany.models.db import Persona, Ticket
from opencompany.models.engine import get_session


# ---------------------------------------------------------------------------
# Test app & client fixture
# ---------------------------------------------------------------------------
@pytest.fixture
async def client(db_engine):
    """Yield an httpx AsyncClient wired to a test FastAPI app with SQLite."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def _override_get_session():
        async with factory() as session:
            yield session

    app = FastAPI()
    app.include_router(router, prefix="/api")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    app.dependency_overrides[get_session] = _override_get_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def seeded_client(db_engine):
    """Client with two pre-seeded personas (CEO + solver)."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="ceo",
                name="Morgan Reeves",
                role="CEO",
                type="manager",
                skills=["strategy", "delegation"],
                backstory="Visionary CEO.",
            )
        )
        session.add(
            Persona(
                id="backend-dev",
                name="Jamie Park",
                role="Backend Dev",
                type="solver",
                skills=["python", "backend"],
                picks_up=["backend", "python"],
                backstory="Versatile engineer.",
            )
        )
        await session.commit()

    async def _override_get_session():
        async with factory() as session:
            yield session

    app = FastAPI()
    app.include_router(router, prefix="/api")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    app.dependency_overrides[get_session] = _override_get_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Personas
# ---------------------------------------------------------------------------
async def test_list_personas_empty(client: AsyncClient):
    resp = await client.get("/api/personas")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_personas_seeded(seeded_client: AsyncClient):
    resp = await seeded_client.get("/api/personas")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    ids = {p["id"] for p in data}
    assert ids == {"ceo", "backend-dev"}


async def test_get_persona(seeded_client: AsyncClient):
    resp = await seeded_client.get("/api/personas/ceo")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Morgan Reeves"
    assert data["type"] == "manager"


async def test_get_persona_not_found(client: AsyncClient):
    resp = await client.get("/api/personas/nonexistent")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------
async def test_create_ticket(client: AsyncClient):
    resp = await client.post(
        "/api/tickets",
        json={
            "title": "Fix login bug",
            "description": "Users can't log in",
            "priority": "high",
            "tags": ["backend"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Fix login bug"
    assert data["priority"] == "high"
    assert data["status"] == "open"
    assert data["tags"] == ["backend"]
    assert data["id"] is not None


async def test_create_ticket_defaults(client: AsyncClient):
    resp = await client.post("/api/tickets", json={"title": "Simple task"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["priority"] == "medium"
    assert data["status"] == "open"
    assert data["tags"] == []


async def test_list_tickets_by_status(client: AsyncClient):
    # Create two tickets
    await client.post("/api/tickets", json={"title": "Ticket A", "priority": "low"})
    await client.post("/api/tickets", json={"title": "Ticket B", "priority": "high"})

    resp = await client.get("/api/tickets?status=open")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    titles = {t["title"] for t in data}
    assert titles == {"Ticket A", "Ticket B"}


async def test_list_tickets_empty_status(client: AsyncClient):
    await client.post("/api/tickets", json={"title": "Open ticket"})
    resp = await client.get("/api/tickets?status=done")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_create_ticket_with_context(client: AsyncClient):
    resp = await client.post(
        "/api/tickets",
        json={
            "title": "SQL injection",
            "tags": ["security"],
            "context": {"file": "auth.py", "line": 42},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["tags"] == ["security"]


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------
async def test_chat_persona_not_found(client: AsyncClient):
    resp = await client.post(
        "/api/chat",
        json={"persona_id": "ghost", "message": "hello"},
    )
    assert resp.status_code == 404


@patch("opencompany.gateway.api.run_persona", new_callable=AsyncMock)
async def test_chat_with_persona(mock_run, seeded_client: AsyncClient):
    mock_run.return_value = "The team is working on security tickets."

    resp = await seeded_client.post(
        "/api/chat",
        json={"persona_id": "ceo", "message": "What is the team doing?"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["response"] == "The team is working on security tickets."
    mock_run.assert_awaited_once()

    # Verify the persona was passed correctly
    called_persona = mock_run.call_args[0][0]
    assert called_persona.id == "ceo"
    assert mock_run.call_args[0][1] == "What is the team doing?"


@patch("opencompany.gateway.api.run_persona", new_callable=AsyncMock)
async def test_chat_returns_agent_response(mock_run, seeded_client: AsyncClient):
    mock_run.return_value = "I've created ticket #1 for this issue."

    resp = await seeded_client.post(
        "/api/chat",
        json={"persona_id": "backend-dev", "message": "Fix the auth module"},
    )
    assert resp.status_code == 200
    assert "ticket #1" in resp.json()["response"]


# ---------------------------------------------------------------------------
# Ticket lifecycle (create → list → verify fields)
# ---------------------------------------------------------------------------
async def test_ticket_lifecycle(client: AsyncClient):
    # 1. Create
    create_resp = await client.post(
        "/api/tickets",
        json={
            "title": "Refactor database layer",
            "description": "Move to async session throughout",
            "priority": "medium",
            "tags": ["backend", "refactor"],
        },
    )
    assert create_resp.status_code == 200
    ticket = create_resp.json()
    ticket_id = ticket["id"]
    assert ticket["status"] == "open"
    assert ticket["assigned_to"] is None

    # 2. List — should appear in open tickets
    list_resp = await client.get("/api/tickets?status=open")
    assert list_resp.status_code == 200
    open_tickets = list_resp.json()
    assert any(t["id"] == ticket_id for t in open_tickets)

    # 3. Not in done tickets
    done_resp = await client.get("/api/tickets?status=done")
    assert done_resp.status_code == 200
    assert not any(t["id"] == ticket_id for t in done_resp.json())


# ---------------------------------------------------------------------------
# Multiple tickets with different priorities
# ---------------------------------------------------------------------------
async def test_multiple_tickets_ordering(client: AsyncClient):
    for title, prio in [("Low", "low"), ("Critical", "critical"), ("High", "high")]:
        await client.post("/api/tickets", json={"title": title, "priority": prio})

    resp = await client.get("/api/tickets?status=open")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    priorities = {t["title"]: t["priority"] for t in data}
    assert priorities["Critical"] == "critical"
    assert priorities["High"] == "high"
    assert priorities["Low"] == "low"


# ---------------------------------------------------------------------------
# Engine: auto-assignment logic (tested directly, not through API)
# ---------------------------------------------------------------------------
async def test_engine_auto_assign(db_engine):
    """Test that the company engine assigns a ticket to the best solver."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    # Seed a solver
    async with factory() as session:
        session.add(
            Persona(
                id="sec-eng",
                name="Alex",
                role="Security Engineer",
                type="solver",
                skills=["security", "python"],
                picks_up=["security"],
                backstory="Fixes security issues.",
            )
        )
        ticket = Ticket(
            title="XSS in templates",
            priority="high",
            tags=["security"],
            created_by="observer",
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        ticket_id = ticket.id

    # Patch the engine's async_session to use our test DB, and mock run_persona
    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine.run_persona", new_callable=AsyncMock),
    ):
        from opencompany.company.engine import _route_ticket

        await _route_ticket(ticket_id)

    # Verify assignment
    async with factory() as session:
        updated = await session.get(Ticket, ticket_id)
        assert updated.assigned_to == "sec-eng"
        assert updated.status == "assigned"


async def test_engine_no_solver_available(db_engine):
    """Ticket stays open when no solver matches."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="frontend-dev",
                name="Chris",
                role="Frontend Dev",
                type="solver",
                skills=["react", "css"],
                picks_up=["frontend"],
                backstory="UI specialist.",
            )
        )
        ticket = Ticket(
            title="Fix backend auth",
            priority="critical",
            tags=["security", "backend"],
            created_by="observer",
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        ticket_id = ticket.id

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine.run_persona", new_callable=AsyncMock),
    ):
        from opencompany.company.engine import _route_ticket

        await _route_ticket(ticket_id)

    async with factory() as session:
        updated = await session.get(Ticket, ticket_id)
        assert updated.assigned_to is None
        assert updated.status == "open"


# ---------------------------------------------------------------------------
# Seed: company.yaml loading
# ---------------------------------------------------------------------------
async def test_seed_company(db_engine, tmp_path):
    """Test that seed_company loads personas from a YAML file."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    config_file = tmp_path / "company.yaml"
    config_file.write_text(
        """
personas:
  - id: test-ceo
    name: Test CEO
    role: CEO
    type: manager
    skills: [strategy]
    backstory: A test CEO.
"""
    )

    with patch("opencompany.company.seed.async_session", factory):
        from opencompany.company.seed import seed_company

        await seed_company(str(config_file))

    async with factory() as session:
        persona = await session.get(Persona, "test-ceo")
        assert persona is not None
        assert persona.name == "Test CEO"
        assert persona.type == "manager"


async def test_seed_company_skips_if_personas_exist(db_engine, tmp_path):
    """Seed is idempotent — skips if personas already exist."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="existing",
                name="Existing",
                role="Dev",
                type="solver",
                backstory="Already here.",
            )
        )
        await session.commit()

    config_file = tmp_path / "company.yaml"
    config_file.write_text(
        """
personas:
  - id: new-hire
    name: New Hire
    role: Dev
    type: solver
    backstory: Should not be seeded.
"""
    )

    with patch("opencompany.company.seed.async_session", factory):
        from opencompany.company.seed import seed_company

        await seed_company(str(config_file))

    async with factory() as session:
        new = await session.get(Persona, "new-hire")
        assert new is None  # should not have been seeded


# ===========================================================================
# Pixel Siege — game development scenario
#
# Simulates a full company workflow: CEO creates high-level tickets,
# PM breaks them down, leads design and create sub-tickets,
# workers execute. Tickets flow: CEO→PM→Leads→Workers.
# ===========================================================================


@pytest.fixture
async def game_company(db_engine):
    """Full NovaCraft Studios org seeded in the test DB."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    personas = [
        Persona(
            id="ceo",
            name="Morgan Reeves",
            role="CEO",
            type="manager",
            skills=["strategy", "delegation", "hiring"],
            backstory="Founded NovaCraft Studios.",
        ),
        Persona(
            id="pm",
            name="Taylor Brooks",
            role="Project Manager",
            type="manager",
            reports_to="ceo",
            skills=["project-management", "planning", "communication"],
            backstory="Turns CEO vision into action.",
        ),
        Persona(
            id="hr",
            name="Quinn Nakamura",
            role="HR Manager",
            type="manager",
            reports_to="ceo",
            skills=["hiring", "team-management"],
            backstory="People-first HR manager.",
        ),
        Persona(
            id="tech-lead",
            name="Dana Kim",
            role="Tech Lead",
            type="manager",
            reports_to="pm",
            skills=["architecture", "python", "javascript", "code-review"],
            picks_up=["backend", "frontend", "architecture", "technical"],
            backstory="Designs architecture, creates dev sub-tickets.",
        ),
        Persona(
            id="marketing-lead",
            name="Riley Cooper",
            role="Marketing Lead",
            type="manager",
            reports_to="pm",
            skills=["marketing", "content", "social-media", "growth"],
            picks_up=["marketing", "content", "growth", "community", "sales"],
            backstory="Builds launch strategies.",
        ),
        Persona(
            id="backend-dev",
            name="Jamie Park",
            role="Backend Developer",
            type="solver",
            reports_to="tech-lead",
            skills=["python", "backend", "api", "game-server", "websockets"],
            picks_up=["backend", "api", "game-server"],
            backstory="Builds game backends.",
        ),
        Persona(
            id="frontend-dev",
            name="Sam Chen",
            role="Frontend Developer",
            type="solver",
            reports_to="tech-lead",
            skills=["javascript", "frontend", "ui", "game-client", "canvas"],
            picks_up=["frontend", "ui", "game-client"],
            backstory="Builds game UIs.",
        ),
        Persona(
            id="content-writer",
            name="Casey Martinez",
            role="Content Writer",
            type="solver",
            reports_to="marketing-lead",
            skills=["copywriting", "sales-pages", "blog", "html", "css"],
            picks_up=["content", "copy", "sales-page", "blog", "website"],
            backstory="Crafts sales pages and marketing copy.",
        ),
    ]

    async with factory() as session:
        for p in personas:
            session.add(p)
        await session.commit()

    async def _override_get_session():
        async with factory() as session:
            yield session

    app = FastAPI()
    app.include_router(router, prefix="/api")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    app.dependency_overrides[get_session] = _override_get_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield {"client": c, "factory": factory}


# ---------------------------------------------------------------------------
# Org chart
# ---------------------------------------------------------------------------
async def test_full_org_is_seeded(game_company):
    """All 8 NovaCraft personas are present and active."""
    client = game_company["client"]
    resp = await client.get("/api/personas")
    assert resp.status_code == 200
    personas = resp.json()
    assert len(personas) == 8
    ids = {p["id"] for p in personas}
    assert ids == {
        "ceo",
        "pm",
        "hr",
        "tech-lead",
        "backend-dev",
        "frontend-dev",
        "marketing-lead",
        "content-writer",
    }


async def test_org_roles(game_company):
    """Verify persona types: 5 managers, 3 solvers."""
    client = game_company["client"]
    resp = await client.get("/api/personas")
    types = [p["type"] for p in resp.json()]
    assert types.count("manager") == 5
    assert types.count("solver") == 3


# ---------------------------------------------------------------------------
# Game dev tickets: cross-team flow
# ---------------------------------------------------------------------------
async def test_researcher_creates_game_design_ticket(game_company):
    """Researcher creates a game-design ticket with tags for the dev team."""
    client = game_company["client"]
    resp = await client.post(
        "/api/tickets",
        json={
            "title": "Design wave-spawning mechanic for Pixel Siege",
            "description": (
                "Players should face increasingly difficult waves of enemies. "
                "Each wave introduces a new enemy type. Difficulty scales with "
                "player count in multiplayer."
            ),
            "priority": "high",
            "tags": ["game-design", "backend", "game-server"],
        },
    )
    assert resp.status_code == 200
    ticket = resp.json()
    assert ticket["status"] == "open"
    assert "game-design" in ticket["tags"]
    assert "game-server" in ticket["tags"]


async def test_backend_ticket_auto_assigned_to_jamie(game_company):
    """A backend/game-server ticket is auto-assigned to the backend dev."""
    factory = game_company["factory"]
    client = game_company["client"]

    # Create the ticket via API
    resp = await client.post(
        "/api/tickets",
        json={
            "title": "Implement WebSocket game lobby",
            "description": "Players need to join and leave lobbies in real time.",
            "priority": "high",
            "tags": ["backend", "game-server", "websockets"],
        },
    )
    ticket_id = resp.json()["id"]

    # Run the engine's auto-assign
    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine.run_persona", new_callable=AsyncMock),
    ):
        from opencompany.company.engine import _route_ticket

        await _route_ticket(ticket_id)

    # Verify Jamie got it
    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        assert ticket.assigned_to == "backend-dev"
        assert ticket.status == "assigned"


async def test_frontend_ticket_auto_assigned_to_sam(game_company):
    """A frontend/game-client ticket is auto-assigned to the frontend dev."""
    factory = game_company["factory"]
    client = game_company["client"]

    resp = await client.post(
        "/api/tickets",
        json={
            "title": "Build tower-placement UI with drag-and-drop",
            "description": "Canvas-based UI for placing towers on the game grid.",
            "priority": "high",
            "tags": ["frontend", "game-client", "ui"],
        },
    )
    ticket_id = resp.json()["id"]

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine.run_persona", new_callable=AsyncMock),
    ):
        from opencompany.company.engine import _route_ticket

        await _route_ticket(ticket_id)

    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        assert ticket.assigned_to == "frontend-dev"
        assert ticket.status == "assigned"


async def test_devops_ticket_auto_assigned_to_jordan(game_company):
    """An infrastructure ticket goes to the DevOps engineer."""
    factory = game_company["factory"]
    client = game_company["client"]

    resp = await client.post(
        "/api/tickets",
        json={
            "title": "Set up CI/CD pipeline for Pixel Siege",
            "description": "GitHub Actions: lint, test, build Docker, deploy to staging.",
            "priority": "medium",
            "tags": ["devops", "ci-cd", "infrastructure"],
        },
    )
    ticket_id = resp.json()["id"]

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine.run_persona", new_callable=AsyncMock),
    ):
        from opencompany.company.engine import _route_ticket

        await _route_ticket(ticket_id)

    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        # devops-eng removed; with new routing, devops/infra tags go to tech-lead
        assert ticket.assigned_to == "tech-lead"
        assert ticket.status == "assigned"


async def test_marketing_ticket_auto_assigned_to_riley(game_company):
    """A marketing ticket goes to the marketing lead."""
    factory = game_company["factory"]
    client = game_company["client"]

    resp = await client.post(
        "/api/tickets",
        json={
            "title": "Write launch announcement for Pixel Siege beta",
            "description": "Blog post + social media campaign for the closed beta.",
            "priority": "medium",
            "tags": ["marketing", "content", "community"],
        },
    )
    ticket_id = resp.json()["id"]

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine.run_persona", new_callable=AsyncMock),
    ):
        from opencompany.company.engine import _route_ticket

        await _route_ticket(ticket_id)

    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        assert ticket.assigned_to == "marketing-lead"
        assert ticket.status == "assigned"


async def test_sales_ticket_auto_assigned_to_content_writer(game_company):
    """A sales/distribution ticket routes via marketing-lead to content-writer."""
    factory = game_company["factory"]
    client = game_company["client"]

    resp = await client.post(
        "/api/tickets",
        json={
            "title": "Negotiate Steam distribution deal",
            "description": "Explore Steam partnership and pricing tiers.",
            "priority": "low",
            "tags": ["sales", "distribution", "partnerships"],
        },
    )
    ticket_id = resp.json()["id"]

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine.run_persona", new_callable=AsyncMock),
    ):
        from opencompany.company.engine import _route_ticket

        await _route_ticket(ticket_id)

    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        # sales-lead removed; sales tags route to marketing-lead
        assert ticket.assigned_to == "marketing-lead"
        assert ticket.status == "assigned"


# ---------------------------------------------------------------------------
# Tech Lead chat: review the backlog
# ---------------------------------------------------------------------------
@patch("opencompany.gateway.api.run_persona", new_callable=AsyncMock)
async def test_tech_lead_reviews_backlog_via_chat(mock_run, game_company):
    """Tech Lead can chat about current tickets and architecture decisions."""
    client = game_company["client"]

    mock_run.return_value = (
        "We have 3 open tickets: WebSocket lobby (backend), "
        "tower-placement UI (frontend), and marketing launch. "
        "I recommend we prioritise the lobby since multiplayer is the "
        "core feature."
    )

    resp = await client.post(
        "/api/chat",
        json={
            "persona_id": "tech-lead",
            "message": "What should we work on first for Pixel Siege?",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "lobby" in data["response"].lower()
    assert mock_run.call_args[0][0].id == "tech-lead"


# ---------------------------------------------------------------------------
# Full sprint: create → assign → solve → review
# ---------------------------------------------------------------------------
async def test_full_sprint_lifecycle(game_company):
    """Simulate a complete sprint: ticket created → assigned → solved → reviewed → done."""
    factory = game_company["factory"]
    client = game_company["client"]

    # 1. Create a ticket (as if researcher filed it)
    resp = await client.post(
        "/api/tickets",
        json={
            "title": "Implement enemy pathfinding algorithm",
            "description": "A* pathfinding for tower-defence enemies on a grid map.",
            "priority": "critical",
            "tags": ["backend", "game-server"],
            "context": {"ref": "docs/plans/pathfinding.md"},
        },
    )
    assert resp.status_code == 200
    ticket_id = resp.json()["id"]

    # 2. Engine auto-assigns to backend-dev
    with (
        patch("opencompany.company.engine.async_session", factory),
        patch(
            "opencompany.company.engine.run_persona",
            new_callable=AsyncMock,
            return_value="Implemented A* pathfinding with grid support.",
        ),
    ):
        from opencompany.company.engine import _route_ticket

        await _route_ticket(ticket_id)

    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        assert ticket.assigned_to == "backend-dev"
        assert ticket.status == "assigned"

    # 3. Solver works on it: status → in_progress → review
    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        ticket.status = "in_progress"
        await session.commit()

    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        ticket.status = "review"
        ticket.result = "Implemented A* pathfinding with grid-based movement."
        await session.commit()

    # 4. Reviewer approves: status → done
    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine.run_persona", new_callable=AsyncMock),
    ):
        from opencompany.company.engine import _trigger_review

        await _trigger_review(ticket_id)

    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        # Engine dispatched reviewer — ticket stays in review until reviewer acts
        assert ticket.status == "review"
        assert ticket.result is not None

        # Simulate reviewer approving
        ticket.status = "done"
        ticket.reviewed_by = "tech-lead"
        await session.commit()

    # 5. Verify final state
    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        assert ticket.status == "done"
        assert ticket.assigned_to == "backend-dev"
        assert ticket.reviewed_by == "tech-lead"
        assert "A*" in ticket.result


# ---------------------------------------------------------------------------
# Workload balancing: two backend tickets, second goes to less-loaded solver
# ---------------------------------------------------------------------------
async def test_workload_balancing_across_solvers(game_company):
    """When backend-dev already has a ticket, a second backend ticket still
    goes to backend-dev if they're the only match — but verify the engine
    considers workload."""
    factory = game_company["factory"]
    client = game_company["client"]

    # Create and assign first ticket to backend-dev
    resp1 = await client.post(
        "/api/tickets",
        json={"title": "Build matchmaking service", "tags": ["backend", "game-server"]},
    )
    t1_id = resp1.json()["id"]

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine.run_persona", new_callable=AsyncMock),
    ):
        from opencompany.company.engine import _route_ticket

        await _route_ticket(t1_id)

    # Create a second backend ticket
    resp2 = await client.post(
        "/api/tickets",
        json={"title": "Add game-state persistence", "tags": ["backend", "api"]},
    )
    t2_id = resp2.json()["id"]

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine.run_persona", new_callable=AsyncMock),
    ):
        await _route_ticket(t2_id)

    # Both go to backend-dev (only solver with backend skills)
    async with factory() as session:
        t1 = await session.get(Ticket, t1_id)
        t2 = await session.get(Ticket, t2_id)
        assert t1.assigned_to == "backend-dev"
        assert t2.assigned_to == "backend-dev"


# ---------------------------------------------------------------------------
# Cross-team game launch: tickets for every department
# ---------------------------------------------------------------------------
async def test_game_launch_creates_cross_team_tickets(game_company):
    """Simulate a game launch creating tickets across all departments."""
    client = game_company["client"]

    launch_tickets = [
        {
            "title": "Final load-test for game servers",
            "priority": "critical",
            "tags": ["backend", "game-server"],
        },
        {
            "title": "Polish tutorial UI flow",
            "priority": "high",
            "tags": ["frontend", "ui", "game-client"],
        },
        {
            "title": "Scale Kubernetes cluster for launch",
            "priority": "critical",
            "tags": ["devops", "cloud", "infrastructure"],
        },
        {
            "title": "Publish launch trailer and press kit",
            "priority": "high",
            "tags": ["marketing", "content"],
        },
        {
            "title": "Finalise platform pricing tiers",
            "priority": "medium",
            "tags": ["sales", "pricing"],
        },
    ]

    created_ids = []
    for t in launch_tickets:
        resp = await client.post("/api/tickets", json=t)
        assert resp.status_code == 200
        created_ids.append(resp.json()["id"])

    # All 5 are open
    resp = await client.get("/api/tickets?status=open")
    assert len(resp.json()) == 5

    # Auto-assign all of them
    factory = game_company["factory"]
    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine.run_persona", new_callable=AsyncMock),
    ):
        from opencompany.company.engine import _route_ticket

        for tid in created_ids:
            await _route_ticket(tid)

    # Verify each went to the right team member (new routing: api tickets → solver matching)
    expected = {
        0: "backend-dev",  # load-test (backend tag)
        1: "frontend-dev",  # tutorial UI (frontend tag)
        2: "backend-dev",  # kubernetes → no devops, falls to backend-dev
        3: "content-writer",  # launch trailer (content tag)
        4: "content-writer",  # pricing (sales tag → marketing-lead → content-writer)
    }

    async with factory() as session:
        for idx, tid in enumerate(created_ids):
            ticket = await session.get(Ticket, tid)
            assert ticket.assigned_to == expected[idx], (
                f"Ticket '{ticket.title}' assigned to {ticket.assigned_to}, "
                f"expected {expected[idx]}"
            )
            assert ticket.status == "assigned"


# ---------------------------------------------------------------------------
# Seed from the real company.yaml
# ---------------------------------------------------------------------------
async def test_seed_real_company_yaml(db_engine):
    """Seed the actual config/company.yaml and verify all 8 personas load."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    with patch("opencompany.company.seed.async_session", factory):
        from opencompany.company.seed import seed_company

        await seed_company("config/company.yaml")

    async with factory() as session:
        from sqlalchemy import func, select

        count = await session.scalar(select(func.count(Persona.id)))
        assert count == 8

        ceo = await session.get(Persona, "ceo")
        assert ceo.name == "Morgan Reeves"

        tech_lead = await session.get(Persona, "tech-lead")
        assert tech_lead.name == "Dana Kim"

        backend = await session.get(Persona, "backend-dev")
        assert "game-server" in backend.skills
