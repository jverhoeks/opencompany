"""Additional coverage tests for the token budget system."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from opencompany.company.budget import (
    check_budget,
    consume_tokens,
    get_all_budget_statuses,
    get_budget_status,
    reset_all_budgets,
    reset_budget,
)
from opencompany.models.db import Persona


@pytest.fixture
async def budget_session(db_engine):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    with patch("opencompany.company.budget.async_session", factory):
        yield factory


# ---------------------------------------------------------------------------
# check_budget
# ---------------------------------------------------------------------------
async def test_check_budget_nonexistent(budget_session):
    """Returns (False, 0) for a persona that does not exist."""
    ok, remaining = await check_budget("ghost")
    assert ok is False
    assert remaining == 0


async def test_check_budget_unlimited(budget_session):
    """Returns (True, 0) when daily_token_budget is 0 (unlimited)."""
    async with budget_session() as session:
        session.add(
            Persona(
                id="unlimited",
                name="Unlimited",
                role="Dev",
                type="solver",
                backstory="No budget limit.",
                daily_token_budget=0,
            )
        )
        await session.commit()

    ok, remaining = await check_budget("unlimited")
    assert ok is True
    assert remaining == 0


async def test_check_budget_auto_reset_on_new_day(budget_session):
    """Budget is auto-reset when the last reset was on a previous day."""
    yesterday = datetime.now(UTC) - timedelta(days=1)
    async with budget_session() as session:
        session.add(
            Persona(
                id="stale",
                name="Stale",
                role="Dev",
                type="solver",
                backstory="Old budget.",
                daily_token_budget=1000,
                tokens_used_today=999,
                budget_reset_at=yesterday,
            )
        )
        await session.commit()

    ok, remaining = await check_budget("stale")
    assert ok is True
    assert remaining == 1000  # reset to full budget


async def test_check_budget_no_reset_at(budget_session):
    """Budget with budget_reset_at=None triggers auto-reset."""
    async with budget_session() as session:
        session.add(
            Persona(
                id="noreset",
                name="No Reset",
                role="Dev",
                type="solver",
                backstory="Never reset.",
                daily_token_budget=500,
                tokens_used_today=300,
                budget_reset_at=None,
            )
        )
        await session.commit()

    ok, remaining = await check_budget("noreset")
    assert ok is True
    assert remaining == 500  # reset because budget_reset_at was None


async def test_check_budget_exhausted(budget_session):
    """Returns (False, 0) when budget is fully consumed today."""
    now = datetime.now(UTC)
    async with budget_session() as session:
        session.add(
            Persona(
                id="exhausted",
                name="Exhausted",
                role="Dev",
                type="solver",
                backstory="Used it all.",
                daily_token_budget=100,
                tokens_used_today=100,
                budget_reset_at=now,
            )
        )
        await session.commit()

    ok, remaining = await check_budget("exhausted")
    assert ok is False
    assert remaining == 0


async def test_check_budget_partial_remaining(budget_session):
    """Returns correct remaining when partially consumed."""
    now = datetime.now(UTC)
    async with budget_session() as session:
        session.add(
            Persona(
                id="partial",
                name="Partial",
                role="Dev",
                type="solver",
                backstory="Some budget left.",
                daily_token_budget=1000,
                tokens_used_today=600,
                budget_reset_at=now,
            )
        )
        await session.commit()

    ok, remaining = await check_budget("partial")
    assert ok is True
    assert remaining == 400


# ---------------------------------------------------------------------------
# consume_tokens
# ---------------------------------------------------------------------------
async def test_consume_tokens_zero_total(budget_session):
    """No-op when total tokens <= 0."""
    async with budget_session() as session:
        session.add(
            Persona(
                id="noop",
                name="Noop",
                role="Dev",
                type="solver",
                backstory="x",
                daily_token_budget=1000,
                tokens_used_today=0,
            )
        )
        await session.commit()

    await consume_tokens("noop", tokens_in=0, tokens_out=0)

    async with budget_session() as session:
        persona = await session.get(Persona, "noop")
        assert persona.tokens_used_today == 0


async def test_consume_tokens_nonexistent(budget_session):
    """No-op for a nonexistent persona."""
    await consume_tokens("ghost", tokens_in=100, tokens_out=50)


async def test_consume_tokens_accumulates(budget_session):
    """Tokens are accumulated on the persona's daily count."""
    async with budget_session() as session:
        session.add(
            Persona(
                id="consumer",
                name="Consumer",
                role="Dev",
                type="solver",
                backstory="x",
                daily_token_budget=5000,
                tokens_used_today=100,
            )
        )
        await session.commit()

    await consume_tokens("consumer", tokens_in=200, tokens_out=100)

    async with budget_session() as session:
        persona = await session.get(Persona, "consumer")
        assert persona.tokens_used_today == 400  # 100 + 200 + 100


async def test_consume_tokens_sets_budget_reset_at(budget_session):
    """Sets budget_reset_at when it was previously None."""
    async with budget_session() as session:
        session.add(
            Persona(
                id="fresh",
                name="Fresh",
                role="Dev",
                type="solver",
                backstory="x",
                daily_token_budget=1000,
                tokens_used_today=0,
                budget_reset_at=None,
            )
        )
        await session.commit()

    await consume_tokens("fresh", tokens_in=50, tokens_out=50)

    async with budget_session() as session:
        persona = await session.get(Persona, "fresh")
        assert persona.budget_reset_at is not None
        assert persona.tokens_used_today == 100


# ---------------------------------------------------------------------------
# reset_budget
# ---------------------------------------------------------------------------
async def test_reset_budget_found(budget_session):
    """Resetting a persona's budget sets tokens_used_today to 0."""
    now = datetime.now(UTC)
    async with budget_session() as session:
        session.add(
            Persona(
                id="reset-me",
                name="Reset Me",
                role="Dev",
                type="solver",
                backstory="x",
                daily_token_budget=1000,
                tokens_used_today=500,
                budget_reset_at=now,
            )
        )
        await session.commit()

    result = await reset_budget("reset-me")
    assert result is True

    async with budget_session() as session:
        persona = await session.get(Persona, "reset-me")
        assert persona.tokens_used_today == 0


async def test_reset_budget_not_found(budget_session):
    """Returns False for a nonexistent persona."""
    result = await reset_budget("ghost")
    assert result is False


# ---------------------------------------------------------------------------
# reset_all_budgets
# ---------------------------------------------------------------------------
async def test_reset_all_budgets(budget_session):
    """Resets budgets for all active personas."""
    now = datetime.now(UTC)
    async with budget_session() as session:
        session.add(
            Persona(
                id="a1",
                name="A1",
                role="Dev",
                type="solver",
                backstory="x",
                daily_token_budget=1000,
                tokens_used_today=500,
                budget_reset_at=now,
            )
        )
        session.add(
            Persona(
                id="a2",
                name="A2",
                role="Dev",
                type="solver",
                backstory="x",
                daily_token_budget=2000,
                tokens_used_today=1000,
                budget_reset_at=now,
            )
        )
        session.add(
            Persona(
                id="fired-p",
                name="Fired",
                role="Dev",
                type="solver",
                backstory="x",
                status="fired",
                daily_token_budget=500,
                tokens_used_today=500,
            )
        )
        await session.commit()

    count = await reset_all_budgets()
    assert count == 2  # only active personas

    async with budget_session() as session:
        a1 = await session.get(Persona, "a1")
        a2 = await session.get(Persona, "a2")
        fired_p = await session.get(Persona, "fired-p")
        assert a1.tokens_used_today == 0
        assert a2.tokens_used_today == 0
        # Fired persona should NOT be reset
        assert fired_p.tokens_used_today == 500


# ---------------------------------------------------------------------------
# get_budget_status / get_all_budget_statuses
# ---------------------------------------------------------------------------
async def test_get_budget_status_found(budget_session):
    """Returns budget dict for an existing persona."""
    now = datetime.now(UTC)
    async with budget_session() as session:
        session.add(
            Persona(
                id="status-dev",
                name="Status Dev",
                role="Dev",
                type="solver",
                backstory="x",
                model_id="gpt-4",
                daily_token_budget=1000,
                tokens_used_today=250,
                budget_reset_at=now,
            )
        )
        await session.commit()

    status = await get_budget_status("status-dev")
    assert status is not None
    assert status["persona_id"] == "status-dev"
    assert status["name"] == "Status Dev"
    assert status["model_id"] == "gpt-4"
    assert status["daily_token_budget"] == 1000
    assert status["tokens_used_today"] == 250
    assert status["remaining"] == 750
    assert status["usage_pct"] == 25.0
    assert status["budget_reset_at"] is not None


async def test_get_budget_status_not_found(budget_session):
    """Returns None for a nonexistent persona."""
    status = await get_budget_status("ghost")
    assert status is None


async def test_get_budget_status_unlimited(budget_session):
    """Unlimited budget returns None for remaining and usage_pct."""
    async with budget_session() as session:
        session.add(
            Persona(
                id="unlim",
                name="Unlim",
                role="Dev",
                type="solver",
                backstory="x",
                daily_token_budget=0,
            )
        )
        await session.commit()

    status = await get_budget_status("unlim")
    assert status["remaining"] is None
    assert status["usage_pct"] is None


async def test_get_all_budget_statuses(budget_session):
    """Returns budget status for all active personas."""
    async with budget_session() as session:
        session.add(
            Persona(
                id="b1",
                name="B1",
                role="Dev",
                type="solver",
                backstory="x",
                daily_token_budget=1000,
            )
        )
        session.add(
            Persona(
                id="b2",
                name="B2",
                role="Dev",
                type="solver",
                backstory="x",
                daily_token_budget=2000,
            )
        )
        await session.commit()

    statuses = await get_all_budget_statuses()
    assert len(statuses) == 2
    ids = {s["persona_id"] for s in statuses}
    assert ids == {"b1", "b2"}
