"""End-to-end tests for the OpenCompany API.

Uses an in-memory SQLite database (no Docker required) and mocks the LLM agent
runner so tests are fast, deterministic, and fully offline.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from opencompany.company.config import CompanyConfig
from opencompany.gateway.api import router
from opencompany.models.db import Persona, Ticket
from opencompany.models.engine import get_session

# ---------------------------------------------------------------------------
# Shared config for engine routing tests
# ---------------------------------------------------------------------------
_GAME_CONFIG = CompanyConfig(
    org_style="hierarchical",
    org_styles={
        "hierarchical": {
            "routing": {"ceo": "pm", "pm": "lead", "lead": "solver"},
            "max_depth": 3,
        },
    },
    roles={
        "ceo": {
            "builtin": True,
            "type": "manager",
            "responsibilities": "Set strategic direction.",
            "tools": ["create_ticket"],
            "routes_to": "pm",
        },
        "hr": {
            "builtin": True,
            "type": "manager",
            "responsibilities": "Handle hiring.",
            "tools": ["hire_persona"],
        },
        "pm": {
            "type": "manager",
            "responsibilities": "Coordinate work.",
            "tools": ["create_ticket"],
            "routes_to": "lead",
        },
        "tech-lead": {
            "type": "lead",
            "tag_match": [
                "backend",
                "frontend",
                "architecture",
                "code",
                "technical",
                "api",
                "database",
                "game-server",
            ],
            "responsibilities": "Design architecture.",
            "tools": ["create_ticket"],
            "routes_to": "solver",
        },
        "marketing-lead": {
            "type": "lead",
            "tag_match": [
                "marketing",
                "content",
                "sales-page",
                "blog",
                "copy",
                "growth",
                "community",
                "sales",
                "website",
            ],
            "responsibilities": "Marketing strategy.",
            "tools": ["create_ticket"],
            "routes_to": "solver",
        },
        "backend-dev": {
            "type": "solver",
            "tag_match": ["backend", "python", "api", "database", "game-server"],
            "responsibilities": "Write backend code.",
            "tools": ["read_file", "write_file"],
        },
        "frontend-dev": {
            "type": "solver",
            "tag_match": ["frontend", "html", "css", "javascript", "ui", "canvas", "game-client"],
            "responsibilities": "Write frontend code.",
            "tools": ["read_file", "write_file"],
        },
        "content-writer": {
            "type": "solver",
            "tag_match": ["content", "copy", "blog", "sales-page", "documentation", "website"],
            "responsibilities": "Write content.",
            "tools": ["read_file", "write_file"],
        },
    },
    personas={},
)


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
# Tickets (via API — requires Redis mock for publish)
# ---------------------------------------------------------------------------
@patch("opencompany.gateway.api.publish", new_callable=AsyncMock)
async def test_create_ticket(mock_pub, client: AsyncClient):
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


@patch("opencompany.gateway.api.publish", new_callable=AsyncMock)
async def test_create_ticket_defaults(mock_pub, client: AsyncClient):
    resp = await client.post("/api/tickets", json={"title": "Simple task"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["priority"] == "medium"
    assert data["status"] == "open"
    assert data["tags"] == []


@patch("opencompany.gateway.api.publish", new_callable=AsyncMock)
async def test_list_tickets_by_status(mock_pub, client: AsyncClient):
    await client.post("/api/tickets", json={"title": "Ticket A", "priority": "low"})
    await client.post("/api/tickets", json={"title": "Ticket B", "priority": "high"})

    resp = await client.get("/api/tickets?status=open")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    titles = {t["title"] for t in data}
    assert titles == {"Ticket A", "Ticket B"}


@patch("opencompany.gateway.api.publish", new_callable=AsyncMock)
async def test_list_tickets_empty_status(mock_pub, client: AsyncClient):
    await client.post("/api/tickets", json={"title": "Open ticket"})
    resp = await client.get("/api/tickets?status=closed")
    assert resp.status_code == 200
    assert resp.json() == []


@patch("opencompany.gateway.api.publish", new_callable=AsyncMock)
async def test_create_ticket_with_context(mock_pub, client: AsyncClient):
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

    called_persona = mock_run.call_args[0][0]
    assert called_persona.id == "ceo"
    # Message may be wrapped with security tags
    assert "What is the team doing?" in mock_run.call_args[0][1]


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
# Ticket lifecycle
# ---------------------------------------------------------------------------
@patch("opencompany.gateway.api.publish", new_callable=AsyncMock)
async def test_ticket_lifecycle(mock_pub, client: AsyncClient):
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

    list_resp = await client.get("/api/tickets?status=open")
    assert list_resp.status_code == 200
    open_tickets = list_resp.json()
    assert any(t["id"] == ticket_id for t in open_tickets)


@patch("opencompany.gateway.api.publish", new_callable=AsyncMock)
async def test_multiple_tickets_ordering(mock_pub, client: AsyncClient):
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

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine.run_persona", new_callable=AsyncMock),
        patch("opencompany.company.engine.load_company_config", return_value=_GAME_CONFIG),
    ):
        from opencompany.company.engine import _route_ticket

        await _route_ticket(ticket_id)

    async with factory() as session:
        updated = await session.get(Ticket, ticket_id)
        assert updated.assigned_to == "sec-eng"
        assert updated.status == "assigned"


async def test_engine_no_solver_available(db_engine):
    """Ticket stays open when no solver is available at all."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        # Only a manager — no solvers in the DB
        session.add(
            Persona(
                id="pm",
                name="Taylor",
                role="Project Manager",
                type="manager",
                skills=["planning"],
                backstory="Coordinator.",
            )
        )
        ticket = Ticket(
            title="Fix backend auth",
            priority="critical",
            tags=["security", "backend"],
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        ticket_id = ticket.id

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine.run_persona", new_callable=AsyncMock),
        patch("opencompany.company.engine.load_company_config", return_value=_GAME_CONFIG),
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
        assert new is None


# ===========================================================================
# Pixel Siege — game development scenario
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
            skills=["project-management", "planning"],
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
            backstory="Designs architecture.",
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
            backstory="Crafts sales pages.",
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
# Config-driven routing tests (create tickets in DB directly, not via API)
# ---------------------------------------------------------------------------
async def test_backend_ticket_auto_assigned_to_jamie(game_company):
    """A backend/game-server ticket is auto-assigned to the backend dev."""
    factory = game_company["factory"]

    async with factory() as session:
        ticket = Ticket(
            title="Implement WebSocket game lobby",
            priority="high",
            tags=["backend", "game-server", "websockets"],
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        ticket_id = ticket.id

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine.run_persona", new_callable=AsyncMock),
        patch("opencompany.company.engine.load_company_config", return_value=_GAME_CONFIG),
    ):
        from opencompany.company.engine import _route_ticket

        await _route_ticket(ticket_id)

    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        assert ticket.assigned_to == "backend-dev"
        assert ticket.status == "assigned"


async def test_frontend_ticket_auto_assigned_to_sam(game_company):
    """A frontend/game-client ticket is auto-assigned to the frontend dev."""
    factory = game_company["factory"]

    async with factory() as session:
        ticket = Ticket(
            title="Build tower-placement UI",
            priority="high",
            tags=["frontend", "game-client", "ui"],
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        ticket_id = ticket.id

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine.run_persona", new_callable=AsyncMock),
        patch("opencompany.company.engine.load_company_config", return_value=_GAME_CONFIG),
    ):
        from opencompany.company.engine import _route_ticket

        await _route_ticket(ticket_id)

    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        assert ticket.assigned_to == "frontend-dev"
        assert ticket.status == "assigned"


async def test_marketing_ticket_auto_assigned(game_company):
    """A marketing ticket from PM routes to marketing-lead via tag_match."""
    factory = game_company["factory"]

    async with factory() as session:
        ticket = Ticket(
            title="Write launch announcement",
            priority="medium",
            tags=["marketing", "content", "community"],
            created_by="pm",
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        ticket_id = ticket.id

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine.run_persona", new_callable=AsyncMock),
        patch("opencompany.company.engine.load_company_config", return_value=_GAME_CONFIG),
    ):
        from opencompany.company.engine import _route_ticket

        await _route_ticket(ticket_id)

    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        assert ticket.assigned_to == "marketing-lead"
        assert ticket.status == "assigned"


async def test_sales_ticket_auto_assigned(game_company):
    """A sales ticket from PM routes to marketing-lead via tag_match."""
    factory = game_company["factory"]

    async with factory() as session:
        ticket = Ticket(
            title="Negotiate Steam distribution deal",
            priority="low",
            tags=["sales", "distribution", "partnerships"],
            created_by="pm",
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        ticket_id = ticket.id

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine.run_persona", new_callable=AsyncMock),
        patch("opencompany.company.engine.load_company_config", return_value=_GAME_CONFIG),
    ):
        from opencompany.company.engine import _route_ticket

        await _route_ticket(ticket_id)

    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        assert ticket.assigned_to == "marketing-lead"
        assert ticket.status == "assigned"


async def test_ceo_ticket_routes_to_pm(game_company):
    """CEO-created ticket routes to PM in hierarchical mode."""
    factory = game_company["factory"]

    async with factory() as session:
        ticket = Ticket(
            title="Build a tic-tac-toe game",
            tags=["product"],
            created_by="ceo",
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        ticket_id = ticket.id

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine.run_persona", new_callable=AsyncMock),
        patch("opencompany.company.engine.load_company_config", return_value=_GAME_CONFIG),
    ):
        from opencompany.company.engine import _route_ticket

        await _route_ticket(ticket_id)

    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        assert ticket.assigned_to == "pm"
        assert ticket.status == "assigned"


# ---------------------------------------------------------------------------
# Tech Lead chat
# ---------------------------------------------------------------------------
@patch("opencompany.gateway.api.run_persona", new_callable=AsyncMock)
async def test_tech_lead_reviews_backlog_via_chat(mock_run, game_company):
    """Tech Lead can chat about current tickets."""
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
    """Simulate a complete sprint: ticket → assigned → solved → reviewed → done."""
    factory = game_company["factory"]

    async with factory() as session:
        ticket = Ticket(
            title="Implement enemy pathfinding algorithm",
            description="A* pathfinding for tower-defence enemies.",
            priority="critical",
            tags=["backend", "game-server"],
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        ticket_id = ticket.id

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine.run_persona", new_callable=AsyncMock),
        patch("opencompany.company.engine.load_company_config", return_value=_GAME_CONFIG),
    ):
        from opencompany.company.engine import _route_ticket

        await _route_ticket(ticket_id)

    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        assert ticket.assigned_to == "backend-dev"
        assert ticket.status == "assigned"

    # Solver works: in_progress → review
    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        ticket.status = "in_progress"
        await session.commit()

    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        ticket.status = "review"
        ticket.result = "Implemented A* pathfinding with grid-based movement."
        await session.commit()

    # Trigger review
    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine.run_persona", new_callable=AsyncMock),
    ):
        from opencompany.company.engine import _trigger_review

        await _trigger_review(ticket_id)

    # Simulate reviewer approving
    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        assert ticket.status == "review"
        ticket.status = "done"
        ticket.reviewed_by = "tech-lead"
        await session.commit()

    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        assert ticket.status == "done"
        assert ticket.assigned_to == "backend-dev"
        assert ticket.reviewed_by == "tech-lead"
        assert "A*" in ticket.result


# ---------------------------------------------------------------------------
# Workload balancing
# ---------------------------------------------------------------------------
async def test_workload_balancing_across_solvers(game_company):
    """Two backend tickets both go to backend-dev (only match)."""
    factory = game_company["factory"]

    async with factory() as session:
        t1 = Ticket(title="Build matchmaking service", tags=["backend", "game-server"])
        t2 = Ticket(title="Add game-state persistence", tags=["backend", "api"])
        session.add(t1)
        session.add(t2)
        await session.commit()
        await session.refresh(t1)
        await session.refresh(t2)
        t1_id, t2_id = t1.id, t2.id

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine.run_persona", new_callable=AsyncMock),
        patch("opencompany.company.engine.load_company_config", return_value=_GAME_CONFIG),
    ):
        from opencompany.company.engine import _route_ticket

        await _route_ticket(t1_id)
        await _route_ticket(t2_id)

    async with factory() as session:
        t1 = await session.get(Ticket, t1_id)
        t2 = await session.get(Ticket, t2_id)
        assert t1.assigned_to == "backend-dev"
        assert t2.assigned_to == "backend-dev"


# ---------------------------------------------------------------------------
# Seed from the real company.yaml (new format: only CEO + HR)
# ---------------------------------------------------------------------------
async def test_seed_real_company_yaml(db_engine):
    """Seed the actual config/company.yaml — only CEO + HR now."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    with patch("opencompany.company.seed.async_session", factory):
        from opencompany.company.seed import seed_company

        await seed_company("config/company.yaml")

    async with factory() as session:
        from sqlalchemy import func, select

        count = await session.scalar(select(func.count(Persona.id)))
        assert count == 2

        ceo = await session.get(Persona, "ceo")
        assert ceo.name == "Morgan Hayes"
        assert ceo.type == "manager"

        hr = await session.get(Persona, "hr")
        assert hr.name == "Quinn Nakamura"


# ---------------------------------------------------------------------------
# Fuzzy tag matching
# ---------------------------------------------------------------------------
def test_fuzzy_tag_matching_exact():
    """Exact tag match scores 1.0."""
    from opencompany.company.taskboard import find_best_solver

    solvers = [{"id": "dev1", "skills": ["backend", "python"], "workload": 0}]
    best = find_best_solver(["backend"], solvers)
    assert best["id"] == "dev1"


def test_fuzzy_tag_matching_substring():
    """Substring match: 'design' matches solver with 'web-design' skill."""
    from opencompany.company.taskboard import find_best_solver

    solvers = [
        {"id": "dev1", "skills": ["web-design", "css"], "workload": 0},
        {"id": "dev2", "skills": ["backend", "api"], "workload": 0},
    ]
    best = find_best_solver(["design"], solvers)
    assert best["id"] == "dev1"


def test_fuzzy_tag_matching_reverse_substring():
    """Reverse substring: solver skill 'ui' matches ticket tag 'ui-design'."""
    from opencompany.company.taskboard import find_best_solver

    solvers = [
        {"id": "designer", "skills": ["ui", "css", "html"], "workload": 0},
        {"id": "backend", "skills": ["python", "api"], "workload": 0},
    ]
    best = find_best_solver(["ui-design"], solvers)
    assert best["id"] == "designer"


# ---------------------------------------------------------------------------
# CEO escalation when no solver matches
# ---------------------------------------------------------------------------
async def test_engine_escalates_to_ceo(db_engine):
    """Ticket escalates to CEO when no solver can handle the tags."""
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
            )
        )
        ticket = Ticket(
            title="Blockchain integration",
            priority="high",
            tags=["blockchain", "crypto"],
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        ticket_id = ticket.id

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine.run_persona", new_callable=AsyncMock),
        patch(
            "opencompany.company.engine.load_company_config",
            return_value=_GAME_CONFIG,
        ),
    ):
        from opencompany.company.engine import _route_ticket

        await _route_ticket(ticket_id)

    async with factory() as session:
        updated = await session.get(Ticket, ticket_id)
        assert updated.assigned_to == "ceo"
        assert updated.status == "assigned"


# ---------------------------------------------------------------------------
# Sweep unassigned tickets
# ---------------------------------------------------------------------------
async def test_sweep_routes_orphaned_tickets(db_engine):
    """Sweep picks up open/unassigned tickets and routes them."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="dev1",
                name="Dev",
                role="Backend Dev",
                type="solver",
                skills=["backend"],
                picks_up=["backend"],
                backstory="A developer.",
            )
        )
        # Orphaned ticket — open, unassigned
        ticket = Ticket(
            title="Fix API bug",
            priority="medium",
            tags=["backend"],
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        ticket_id = ticket.id

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine.run_persona", new_callable=AsyncMock),
        patch(
            "opencompany.company.engine.load_company_config",
            return_value=_GAME_CONFIG,
        ),
    ):
        from opencompany.company.engine import sweep_unassigned_tickets

        count = await sweep_unassigned_tickets()

    assert count == 1
    async with factory() as session:
        updated = await session.get(Ticket, ticket_id)
        assert updated.assigned_to == "dev1"
        assert updated.status == "assigned"


# ===========================================================================
# Auth enforcement
# ===========================================================================


@pytest.fixture
async def auth_client(db_engine, monkeypatch):
    """Client with API_KEY set — all endpoints require bearer auth."""
    monkeypatch.setenv("API_KEY", "test-secret-key")

    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def _override_get_session():
        async with factory() as session:
            yield session

    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_session] = _override_get_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_api_rejects_without_key(auth_client: AsyncClient):
    """Requests without a bearer token get 401 when API_KEY is set."""
    endpoints = [
        ("GET", "/api/personas"),
        ("GET", "/api/tickets"),
        ("POST", "/api/tickets"),
        ("POST", "/api/chat"),
        ("PATCH", "/api/tickets/1"),
    ]
    for method, path in endpoints:
        resp = await auth_client.request(method, path)
        assert resp.status_code == 401, (
            f"{method} {path} should return 401, got {resp.status_code}"
        )


async def test_api_rejects_wrong_key(auth_client: AsyncClient):
    """Requests with an incorrect bearer token get 401."""
    resp = await auth_client.get(
        "/api/personas",
        headers={"Authorization": "Bearer wrong-key"},
    )
    assert resp.status_code == 401


async def test_api_accepts_correct_key(auth_client: AsyncClient):
    """Requests with the correct bearer token succeed."""
    resp = await auth_client.get(
        "/api/personas",
        headers={"Authorization": "Bearer test-secret-key"},
    )
    assert resp.status_code == 200


# ===========================================================================
# Dashboard auth enforcement
# ===========================================================================


@pytest.fixture
async def dashboard_client(db_engine, monkeypatch):
    """Client with both API and dashboard routers, API_KEY set."""
    from opencompany.gateway.dashboard import router as dashboard_router

    monkeypatch.setenv("API_KEY", "test-secret-key")

    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def _override_get_session():
        async with factory() as session:
            yield session

    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.include_router(dashboard_router)

    app.dependency_overrides[get_session] = _override_get_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_dashboard_stream_requires_auth(dashboard_client: AsyncClient):
    """GET /api/dashboard/stream returns 401 when no bearer token is provided."""
    resp = await dashboard_client.get("/api/dashboard/stream")
    assert resp.status_code == 401


async def test_dashboard_overview_requires_auth(dashboard_client: AsyncClient):
    """GET /api/dashboard/overview returns 401 when no bearer token is provided."""
    resp = await dashboard_client.get("/api/dashboard/overview")
    assert resp.status_code == 401


async def test_overseer_messages_requires_auth(dashboard_client: AsyncClient):
    """GET /api/overseer/messages returns 401 when no bearer token is provided."""
    resp = await dashboard_client.get("/api/overseer/messages")
    assert resp.status_code == 401


async def test_overseer_reply_requires_auth(dashboard_client: AsyncClient):
    """POST /api/overseer/messages/1/reply returns 401 when no bearer token is provided."""
    resp = await dashboard_client.post(
        "/api/overseer/messages/1/reply",
        json={"reply": "test reply"},
    )
    assert resp.status_code == 401


# ===========================================================================
# Budget system
# ===========================================================================


async def test_budget_check_unlimited(db_engine):
    """Persona with budget=0 always has budget (unlimited)."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="dev-free",
                name="Free Dev",
                role="Dev",
                type="solver",
                backstory="Unlimited budget.",
                daily_token_budget=0,
            )
        )
        await session.commit()

    with patch("opencompany.company.budget.async_session", factory):
        from opencompany.company.budget import check_budget

        has_budget, remaining = await check_budget("dev-free")
        assert has_budget is True
        assert remaining == 0  # unlimited


async def test_budget_check_and_consume(db_engine):
    """Budget decreases as tokens are consumed, blocks when exceeded."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="dev-budget",
                name="Budget Dev",
                role="Dev",
                type="solver",
                backstory="Limited budget.",
                daily_token_budget=1000,
            )
        )
        await session.commit()

    with patch("opencompany.company.budget.async_session", factory):
        from opencompany.company.budget import check_budget, consume_tokens

        has_budget, remaining = await check_budget("dev-budget")
        assert has_budget is True
        assert remaining == 1000

        await consume_tokens("dev-budget", 400, 200)

        has_budget, remaining = await check_budget("dev-budget")
        assert has_budget is True
        assert remaining == 400

        # Consume the rest
        await consume_tokens("dev-budget", 300, 200)

        has_budget, remaining = await check_budget("dev-budget")
        assert has_budget is False
        assert remaining == 0


async def test_budget_reset(db_engine):
    """Resetting budget clears tokens_used_today."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="dev-reset",
                name="Reset Dev",
                role="Dev",
                type="solver",
                backstory="Will be reset.",
                daily_token_budget=500,
            )
        )
        await session.commit()

    with patch("opencompany.company.budget.async_session", factory):
        from opencompany.company.budget import check_budget, consume_tokens, reset_budget

        await consume_tokens("dev-reset", 300, 300)
        has_budget, _ = await check_budget("dev-reset")
        assert has_budget is False

        found = await reset_budget("dev-reset")
        assert found is True

        has_budget, remaining = await check_budget("dev-reset")
        assert has_budget is True
        assert remaining == 500


async def test_budget_status(db_engine):
    """get_budget_status returns correct fields."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="dev-status",
                name="Status Dev",
                role="Dev",
                type="solver",
                backstory="Check status.",
                daily_token_budget=10000,
                model_id="anthropic/claude-haiku-4-5-20251001",
            )
        )
        await session.commit()

    with patch("opencompany.company.budget.async_session", factory):
        from opencompany.company.budget import get_budget_status

        status = await get_budget_status("dev-status")
        assert status is not None
        assert status["persona_id"] == "dev-status"
        assert status["daily_token_budget"] == 10000
        assert status["tokens_used_today"] == 0
        assert status["remaining"] == 10000
        assert status["usage_pct"] == 0.0
        assert status["model_id"] == "anthropic/claude-haiku-4-5-20251001"


async def test_budget_api_list(db_engine):
    """GET /api/budget returns budget statuses for all active personas."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="ceo-b",
                name="CEO",
                role="CEO",
                type="manager",
                backstory="CEO",
                daily_token_budget=100000,
            )
        )
        session.add(
            Persona(
                id="dev-b",
                name="Dev",
                role="Dev",
                type="solver",
                backstory="Dev",
                daily_token_budget=200000,
            )
        )
        await session.commit()

    async def _override_get_session():
        async with factory() as session:
            yield session

    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_session] = _override_get_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        with patch("opencompany.company.budget.async_session", factory):
            resp = await c.get("/api/budget")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 2
            ids = {b["persona_id"] for b in data}
            assert ids == {"ceo-b", "dev-b"}


async def test_budget_api_reset(db_engine):
    """POST /api/budget/{id}/reset resets a persona's budget."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="dev-r",
                name="Dev",
                role="Dev",
                type="solver",
                backstory="Dev",
                daily_token_budget=1000,
                tokens_used_today=999,
            )
        )
        await session.commit()

    async def _override_get_session():
        async with factory() as session:
            yield session

    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_session] = _override_get_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        with patch("opencompany.company.budget.async_session", factory):
            resp = await c.post("/api/budget/dev-r/reset")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

            # Verify it was reset
            resp = await c.get("/api/budget/dev-r")
            assert resp.status_code == 200
            assert resp.json()["tokens_used_today"] == 0


# ===========================================================================
# Model ID in seed
# ===========================================================================


async def test_seed_populates_model_id(db_engine, tmp_path):
    """Seed populates model_id and daily_token_budget from role config."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    config_file = tmp_path / "company.yaml"
    config_file.write_text(
        """
roles:
  ceo:
    builtin: true
    type: manager
    model: anthropic/claude-sonnet-4-5-20250929
    daily_token_budget: 100000
    tools: [create_ticket]
personas:
  ceo:
    role: ceo
    name: Test CEO
    backstory: A visionary.
"""
    )

    with patch("opencompany.company.seed.async_session", factory):
        from opencompany.company.seed import seed_company

        await seed_company(str(config_file))

    async with factory() as session:
        ceo = await session.get(Persona, "ceo")
        assert ceo is not None
        assert ceo.model_id == "anthropic/claude-sonnet-4-5-20250929"
        assert ceo.daily_token_budget == 100000


# ===========================================================================
# Budget enforcement in engine
# ===========================================================================


async def test_engine_budget_blocks_over_budget_persona(db_engine):
    """Persona over budget gets blocked state, task is skipped."""
    from datetime import UTC, datetime

    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="over-budget",
                name="Over Budget",
                role="Dev",
                type="solver",
                backstory="Over budget dev.",
                daily_token_budget=100,
                tokens_used_today=200,
                budget_reset_at=datetime.now(UTC),
            )
        )
        ticket = Ticket(
            title="Test task",
            tags=["backend"],
            created_by="test",
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine.run_persona", new_callable=AsyncMock) as mock_run,
        patch("opencompany.company.budget.async_session", factory),
    ):
        from opencompany.company.engine import _spawn_persona_task

        # Get the persona object
        async with factory() as session:
            persona = await session.get(Persona, "over-budget")

        _spawn_persona_task(persona, "Do the work", "test-budget-block")

        # Wait for the background task to complete
        import asyncio

        await asyncio.sleep(0.5)

        # run_persona should NOT have been called (budget blocked)
        mock_run.assert_not_called()

    # Persona should be in blocked state
    async with factory() as session:
        persona = await session.get(Persona, "over-budget")
        assert persona.activity_state == "blocked"


# ===========================================================================
# Heartbeat
# ===========================================================================


async def test_heartbeat_triggers_idle_personas(db_engine):
    """Heartbeat job spawns tasks for idle personas with budget."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="idle-dev",
                name="Idle Dev",
                role="Dev",
                type="solver",
                backstory="Idle dev.",
                activity_state="idle",
                daily_token_budget=100000,
            )
        )
        await session.commit()

    with (
        patch("opencompany.models.engine.async_session", factory),
        patch("opencompany.company.budget.async_session", factory),
        patch("opencompany.company.engine._spawn_persona_task") as mock_spawn,
    ):
        from opencompany.company.scheduler import _persona_heartbeat_job

        await _persona_heartbeat_job()

    mock_spawn.assert_called_once()
    call_args = mock_spawn.call_args
    assert call_args[0][0].id == "idle-dev"
    assert "heartbeat-idle-dev" in call_args[0][2]


async def test_heartbeat_skips_busy_personas(db_engine):
    """Heartbeat skips personas in 'working' state."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="busy-dev",
                name="Busy Dev",
                role="Dev",
                type="solver",
                backstory="Working.",
                activity_state="working",
                daily_token_budget=100000,
            )
        )
        await session.commit()

    with (
        patch("opencompany.models.engine.async_session", factory),
        patch("opencompany.company.budget.async_session", factory),
        patch("opencompany.company.engine._spawn_persona_task") as mock_spawn,
    ):
        from opencompany.company.scheduler import _persona_heartbeat_job

        await _persona_heartbeat_job()

    mock_spawn.assert_not_called()


async def test_heartbeat_skips_over_budget(db_engine):
    """Heartbeat skips personas who are over budget."""
    from datetime import UTC, datetime

    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="broke-dev",
                name="Broke Dev",
                role="Dev",
                type="solver",
                backstory="Over budget.",
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
    ):
        from opencompany.company.scheduler import _persona_heartbeat_job

        await _persona_heartbeat_job()

    mock_spawn.assert_not_called()
