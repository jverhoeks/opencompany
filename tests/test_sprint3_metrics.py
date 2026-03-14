"""Tests for Sprint 3: efficiency metrics endpoint (P5)."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from opencompany.models.db import Persona, Ticket, WorkLog


@pytest.fixture
async def factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


async def test_metrics_returns_per_persona_data(db_engine):
    """Metrics endpoint returns tasks_completed, total_tokens, tokens_per_task."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="metrics-dev",
                name="Metrics Dev",
                role="Dev",
                type="solver",
                backstory="x",
            )
        )
        t1 = Ticket(
            title="Task 1",
            tags=["x"],
            status="done",
            tokens_in=500,
            tokens_out=200,
            assigned_to="metrics-dev",
        )
        session.add(t1)
        await session.flush()
        session.add(
            WorkLog(
                persona_id="metrics-dev",
                action="done",
                ticket_id=t1.id,
                duration_sec=30,
            )
        )

        t2 = Ticket(
            title="Task 2",
            tags=["x"],
            status="done",
            tokens_in=300,
            tokens_out=100,
            assigned_to="metrics-dev",
        )
        session.add(t2)
        await session.flush()
        session.add(
            WorkLog(
                persona_id="metrics-dev",
                action="done",
                ticket_id=t2.id,
                duration_sec=20,
            )
        )
        await session.commit()

    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from opencompany.gateway.api import router
    from opencompany.models.engine import get_session

    app = FastAPI()
    app.include_router(router, prefix="/api")

    async def override_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/metrics/efficiency")
        assert resp.status_code == 200
        data = resp.json()

    assert len(data) >= 1
    dev = next(m for m in data if m["persona_id"] == "metrics-dev")
    assert dev["tasks_completed"] == 2
    assert dev["total_tokens"] == 1100  # (500+200) + (300+100)
    assert dev["tokens_per_task"] == 550
    assert dev["avg_duration_sec"] == 25.0


async def test_metrics_empty_when_no_work(db_engine):
    """Metrics endpoint returns empty list when no completed work."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from opencompany.gateway.api import router
    from opencompany.models.engine import get_session

    app = FastAPI()
    app.include_router(router, prefix="/api")

    async def override_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/metrics/efficiency")
        assert resp.status_code == 200
        assert resp.json() == []
