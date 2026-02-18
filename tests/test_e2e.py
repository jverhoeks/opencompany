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
