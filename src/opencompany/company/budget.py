"""Token budget system: check, consume, reset, and report per-persona budgets."""

import logging
from datetime import UTC, datetime

from sqlalchemy import select

from opencompany.models.db import Persona
from opencompany.models.engine import async_session

logger = logging.getLogger(__name__)


async def check_budget(persona_id: str) -> tuple[bool, int]:
    """Check if a persona has budget remaining. Auto-resets on new day.

    Returns (has_budget, remaining). If daily_token_budget is 0, budget is unlimited.
    """
    async with async_session() as session:
        persona = await session.get(Persona, persona_id)
        if not persona:
            return False, 0

        if persona.daily_token_budget == 0:
            return True, 0  # unlimited

        # Auto-reset on new day
        now = datetime.now(UTC)
        if persona.budget_reset_at is None or persona.budget_reset_at.date() < now.date():
            persona.tokens_used_today = 0
            persona.budget_reset_at = now
            await session.commit()

        remaining = persona.daily_token_budget - persona.tokens_used_today
        return remaining > 0, max(remaining, 0)


async def consume_tokens(persona_id: str, tokens_in: int, tokens_out: int) -> None:
    """Accumulate token usage on a persona's daily budget."""
    total = tokens_in + tokens_out
    if total <= 0:
        return

    async with async_session() as session:
        persona = await session.get(Persona, persona_id)
        if not persona:
            return

        persona.tokens_used_today = (persona.tokens_used_today or 0) + total
        if persona.budget_reset_at is None:
            persona.budget_reset_at = datetime.now(UTC)
        await session.commit()
        logger.info(
            "Persona %s consumed %d tokens (total today: %d/%d)",
            persona_id,
            total,
            persona.tokens_used_today,
            persona.daily_token_budget,
        )


async def reset_budget(persona_id: str) -> bool:
    """Reset a single persona's daily budget. Returns True if found."""
    async with async_session() as session:
        persona = await session.get(Persona, persona_id)
        if not persona:
            return False
        persona.tokens_used_today = 0
        persona.budget_reset_at = datetime.now(UTC)
        await session.commit()
        logger.info("Reset budget for persona %s", persona_id)
        return True


async def reset_all_budgets() -> int:
    """Reset all persona budgets. Returns count of personas reset."""
    async with async_session() as session:
        result = await session.execute(select(Persona).where(Persona.status == "active"))
        personas = result.scalars().all()
        now = datetime.now(UTC)
        for p in personas:
            p.tokens_used_today = 0
            p.budget_reset_at = now
        await session.commit()
        logger.info("Reset budgets for %d personas", len(personas))
        return len(personas)


async def get_budget_status(persona_id: str) -> dict | None:
    """Get budget status for a single persona."""
    async with async_session() as session:
        persona = await session.get(Persona, persona_id)
        if not persona:
            return None
        return _persona_budget_dict(persona)


async def get_all_budget_statuses() -> list[dict]:
    """Get budget status for all active personas."""
    async with async_session() as session:
        result = await session.execute(select(Persona).where(Persona.status == "active"))
        return [_persona_budget_dict(p) for p in result.scalars().all()]


def _persona_budget_dict(persona: Persona) -> dict:
    budget = persona.daily_token_budget
    used = persona.tokens_used_today or 0
    return {
        "persona_id": persona.id,
        "name": persona.name,
        "model_id": persona.model_id,
        "daily_token_budget": budget,
        "tokens_used_today": used,
        "remaining": max(budget - used, 0) if budget > 0 else None,
        "usage_pct": round(used / budget * 100, 1) if budget > 0 else None,
        "budget_reset_at": (
            persona.budget_reset_at.isoformat() if persona.budget_reset_at else None
        ),
    }
