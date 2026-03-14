"""Tests for Sprint 8: S1 spawn_subagent, S2 CompanyHooks."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from opencompany.agents.hooks import CompanyHooks
from opencompany.company.trust import TOOL_TIER_REQUIREMENTS, filter_tools_by_tier
from opencompany.models.db import Persona


@pytest.fixture
async def factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# S1: spawn_subagent tool
# ---------------------------------------------------------------------------
class TestSpawnSubagent:
    def test_tool_registered(self):
        from opencompany.agents.tools import ALL_TOOLS

        assert "spawn_subagent" in ALL_TOOLS

    def test_requires_solver_tier(self):
        assert TOOL_TIER_REQUIREMENTS["spawn_subagent"] == "solver"

    def test_external_denied(self):
        allowed, denied = filter_tools_by_tier(["spawn_subagent"], "external")
        assert "spawn_subagent" in denied

    def test_solver_allowed(self):
        allowed, denied = filter_tools_by_tier(["spawn_subagent"], "solver")
        assert "spawn_subagent" in allowed


# ---------------------------------------------------------------------------
# S2: CompanyHooks
# ---------------------------------------------------------------------------
class TestCompanyHooks:
    async def test_on_tool_use_records_calls(self):
        hooks = CompanyHooks(persona_id="dev-1", ticket_id=42)
        await hooks.on_tool_use("write_file")
        await hooks.on_tool_use("read_file")
        assert hooks.tool_calls == ["write_file", "read_file"]

    async def test_on_invocation_complete_consumes_budget(self, factory):
        async with factory() as session:
            session.add(
                Persona(
                    id="hook-dev",
                    name="Hook Dev",
                    role="Dev",
                    type="solver",
                    backstory="x",
                    daily_token_budget=100000,
                )
            )
            await session.commit()

        hooks = CompanyHooks(persona_id="hook-dev", ticket_id=None)

        with (
            patch("opencompany.company.budget.async_session", factory),
            patch("opencompany.events.bus.get_redis", new_callable=AsyncMock),
        ):
            await hooks.on_invocation_complete(500, 200)

        async with factory() as session:
            persona = await session.get(Persona, "hook-dev")
            assert persona.tokens_used_today == 700

    async def test_summary(self):
        hooks = CompanyHooks(persona_id="dev-1", ticket_id=42)
        await hooks.on_tool_use("write_file")
        summary = hooks.summary()
        assert summary["persona_id"] == "dev-1"
        assert summary["ticket_id"] == 42
        assert summary["tool_count"] == 1
