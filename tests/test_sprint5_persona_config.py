"""Tests for Sprint 5: P6 DB-backed persona config, snapshots, config API."""

from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from opencompany.models.db import CompanySnapshot, PersonaConfig, Ticket


@pytest.fixture
async def factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# PersonaConfig model
# ---------------------------------------------------------------------------
class TestPersonaConfigModel:
    async def test_create_persona_config(self, factory):
        async with factory() as session:
            pc = PersonaConfig(
                id="dev-1",
                name="Dev One",
                role="developer",
                trust="solver",
                skills=["python", "backend"],
                budget_tokens_daily=50000,
                instructions="Write clean code.",
                personality={"traits": ["focused"]},
            )
            session.add(pc)
            await session.commit()
            await session.refresh(pc)

        async with factory() as session:
            loaded = await session.get(PersonaConfig, "dev-1")
            assert loaded.name == "Dev One"
            assert loaded.trust == "solver"
            assert loaded.skills == ["python", "backend"]
            assert loaded.instructions == "Write clean code."
            assert loaded.personality == {"traits": ["focused"]}

    async def test_company_snapshot_model(self, factory):
        async with factory() as session:
            snap = CompanySnapshot(
                trigger="manual",
                snapshot={"personas": [], "tickets": {"open": 5}},
            )
            session.add(snap)
            await session.commit()
            await session.refresh(snap)

        async with factory() as session:
            from sqlalchemy import select

            result = await session.execute(select(CompanySnapshot))
            loaded = result.scalars().first()
            assert loaded.trigger == "manual"
            assert loaded.snapshot["tickets"]["open"] == 5


# ---------------------------------------------------------------------------
# boot_persona_configs
# ---------------------------------------------------------------------------
class TestBootPersonaConfigs:
    async def test_boot_seeds_from_yaml(self, factory, tmp_path):
        import yaml

        yaml_file = tmp_path / "company.yaml"
        yaml_file.write_text(
            yaml.dump(
                {
                    "org_style": "hierarchical",
                    "org_styles": {},
                    "roles": {
                        "ceo": {
                            "type": "manager",
                            "tag_match": ["strategy"],
                            "daily_token_budget": 100000,
                            "responsibilities": "Lead the company.",
                            "personality": {"traits": ["bold"]},
                        },
                        "dev": {
                            "type": "solver",
                            "tag_match": ["backend"],
                            "daily_token_budget": 50000,
                            "responsibilities": "Write code.",
                        },
                    },
                    "personas": {},
                }
            )
        )

        with patch("opencompany.models.engine.async_session", factory):
            from opencompany.company.config import boot_persona_configs

            count = await boot_persona_configs(str(yaml_file))

        assert count == 2

        async with factory() as session:
            ceo = await session.get(PersonaConfig, "ceo")
            assert ceo is not None
            assert ceo.trust == "full"
            assert ceo.budget_tokens_daily == 100000
            assert ceo.personality == {"traits": ["bold"]}

            dev = await session.get(PersonaConfig, "dev")
            assert dev is not None
            assert dev.trust == "solver"

    async def test_boot_skips_if_already_seeded(self, factory):
        async with factory() as session:
            session.add(
                PersonaConfig(
                    id="existing",
                    name="Existing",
                    role="dev",
                )
            )
            await session.commit()

        with patch("opencompany.models.engine.async_session", factory):
            from opencompany.company.config import boot_persona_configs

            count = await boot_persona_configs()

        assert count == 0


# ---------------------------------------------------------------------------
# snapshot_company
# ---------------------------------------------------------------------------
class TestSnapshotCompany:
    async def test_snapshot_captures_state(self, factory):
        async with factory() as session:
            session.add(PersonaConfig(id="snap-dev", name="Snap Dev", role="dev"))
            session.add(Ticket(title="Open task", tags=["x"], status="open"))
            session.add(Ticket(title="Done task", tags=["x"], status="done"))
            await session.commit()

        with patch("opencompany.models.engine.async_session", factory):
            from opencompany.company.scheduler import snapshot_company

            await snapshot_company("test")

        async with factory() as session:
            from sqlalchemy import select

            result = await session.execute(select(CompanySnapshot))
            snap = result.scalars().first()
            assert snap is not None
            assert snap.trigger == "test"
            assert len(snap.snapshot["personas"]) == 1
            assert snap.snapshot["tickets"]["open"] == 1
            assert snap.snapshot["tickets"]["done"] == 1

    async def test_snapshot_skips_empty_config(self, factory):
        """No PersonaConfigs → no snapshot written."""
        with patch("opencompany.models.engine.async_session", factory):
            from opencompany.company.scheduler import snapshot_company

            await snapshot_company("test")

        async with factory() as session:
            from sqlalchemy import select

            result = await session.execute(select(CompanySnapshot))
            assert result.scalars().first() is None


# ---------------------------------------------------------------------------
# Config API endpoints
# ---------------------------------------------------------------------------
class TestConfigAPI:
    async def test_list_persona_configs(self, db_engine):
        factory = async_sessionmaker(db_engine, expire_on_commit=False)

        async with factory() as session:
            session.add(
                PersonaConfig(
                    id="api-dev",
                    name="API Dev",
                    role="dev",
                    instructions="Code well.",
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
            resp = await client.get("/api/config/personas")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["id"] == "api-dev"
            assert data[0]["instructions"] == "Code well."

    async def test_patch_persona_config(self, db_engine):
        factory = async_sessionmaker(db_engine, expire_on_commit=False)

        async with factory() as session:
            session.add(
                PersonaConfig(
                    id="patch-dev",
                    name="Patch Dev",
                    role="dev",
                    instructions="Old instructions.",
                    budget_tokens_daily=1000,
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
            resp = await client.patch(
                "/api/config/personas/patch-dev",
                json={
                    "instructions": "New instructions.",
                    "budget_tokens_daily": 5000,
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["instructions"] == "New instructions."
            assert data["budget_tokens_daily"] == 5000
            assert data["updated_by"] == "overseer"

    async def test_patch_nonexistent_config(self, db_engine):
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
            resp = await client.patch(
                "/api/config/personas/ghost",
                json={"instructions": "Nope."},
            )
            assert resp.status_code == 404
