"""Tests for the dashboard overview endpoint."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from opencompany.gateway.dashboard import router
from opencompany.models.db import Persona, Ticket, WorkLog
from opencompany.models.engine import get_session


@pytest.fixture
async def dashboard_client(db_engine):
    """Yield an httpx AsyncClient wired to the dashboard router with SQLite."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def _override():
        async with factory() as session:
            yield session

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = _override

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield {"client": c, "factory": factory}


async def test_overview_empty(dashboard_client):
    """Overview returns empty structures when no data exists."""
    resp = await dashboard_client["client"].get("/api/dashboard/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["personas"] == []
    assert data["tickets"] == []
    assert data["status_counts"] == {}
    assert data["work_log"] == []


async def test_overview_with_personas_and_tickets(dashboard_client):
    """Overview includes persona workload and ticket status counts."""
    factory = dashboard_client["factory"]

    async with factory() as session:
        session.add(
            Persona(
                id="dev-1",
                name="Jamie",
                role="Dev",
                type="solver",
                skills=["python"],
            )
        )
        session.add(
            Ticket(
                title="Fix bug",
                priority="high",
                status="assigned",
                tags=["backend"],
                assigned_to="dev-1",
            )
        )
        session.add(
            Ticket(
                title="Another task",
                priority="low",
                status="open",
                tags=[],
            )
        )
        await session.commit()

    resp = await dashboard_client["client"].get("/api/dashboard/overview")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["personas"]) == 1
    assert data["personas"][0]["id"] == "dev-1"
    assert data["personas"][0]["workload"] == 1

    assert len(data["tickets"]) == 2
    assert data["status_counts"]["assigned"] == 1
    assert data["status_counts"]["open"] == 1


async def test_overview_work_log(dashboard_client):
    """Overview includes recent work log entries."""
    factory = dashboard_client["factory"]

    async with factory() as session:
        session.add(
            Persona(
                id="dev-1",
                name="Jamie",
                role="Dev",
                type="solver",
                skills=["python"],
            )
        )
        await session.flush()
        session.add(
            WorkLog(
                persona_id="dev-1",
                action="created",
                details="Created a ticket",
            )
        )
        await session.commit()

    resp = await dashboard_client["client"].get("/api/dashboard/overview")
    data = resp.json()
    assert len(data["work_log"]) == 1
    assert data["work_log"][0]["action"] == "created"
    assert data["work_log"][0]["persona_id"] == "dev-1"
