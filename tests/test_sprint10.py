"""Tests for Sprint 10: SI5 soul history API + S5 OTEL config."""

from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from opencompany.models.db import SoulVersion


@pytest.fixture
async def factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# SI5: Soul history API
# ---------------------------------------------------------------------------
class TestSoulAPI:
    async def test_get_soul(self, db_engine, tmp_path):
        soul_file = tmp_path / "soul.md"
        soul_file.write_text("# Test Soul\n1. Be good.")

        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient

        from opencompany.gateway.api import router

        app = FastAPI()
        app.include_router(router, prefix="/api")

        with patch("opencompany.company.soul._SOUL_PATH", soul_file):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/soul")
                assert resp.status_code == 200
                assert "Be good" in resp.json()["content"]

    async def test_soul_history(self, db_engine):
        factory = async_sessionmaker(db_engine, expire_on_commit=False)

        async with factory() as session:
            session.add(
                SoulVersion(
                    version=1,
                    content="v1 content",
                    diff="",
                    rationale="Initial",
                    proposed_by="system",
                )
            )
            session.add(
                SoulVersion(
                    version=2,
                    content="v2 content",
                    diff="+new rule",
                    rationale="Improvement",
                    proposed_by="analyst",
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
            resp = await client.get("/api/soul/history")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 2
            # Most recent first
            assert data[0]["version"] == 2
            assert data[0]["proposed_by"] == "analyst"
            assert data[1]["version"] == 1

    async def test_soul_rollback_api(self, db_engine, tmp_path):
        factory = async_sessionmaker(db_engine, expire_on_commit=False)
        soul_file = tmp_path / "soul.md"
        soul_file.write_text("# Version: 2\nCurrent")

        async with factory() as session:
            session.add(
                SoulVersion(
                    version=1,
                    content="# Version: 1\nOriginal",
                    proposed_by="system",
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

        with (
            patch("opencompany.company.soul._SOUL_PATH", soul_file),
            patch("opencompany.company.soul.async_session", factory),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/api/soul/rollback/1")
                assert resp.status_code == 200
                assert "v1" in resp.json()["message"]

        assert "Original" in soul_file.read_text()


# ---------------------------------------------------------------------------
# S5: OpenTelemetry entrypoint
# ---------------------------------------------------------------------------
class TestOTELConfig:
    def test_entrypoint_script_exists(self):
        from pathlib import Path

        assert Path("docker-entrypoint.sh").exists()

    def test_entrypoint_has_otel_toggle(self):
        from pathlib import Path

        content = Path("docker-entrypoint.sh").read_text()
        assert "OTEL_ENABLED" in content
        assert "opentelemetry-instrument" in content

    def test_dockerfile_copies_soul_and_sops(self):
        from pathlib import Path

        content = Path("Dockerfile").read_text()
        assert "soul.md" in content
        assert "sops/" in content
        assert "OTEL_SERVICE_NAME" in content
