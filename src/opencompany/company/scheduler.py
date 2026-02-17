"""Schedules observer personas to run on cron triggers."""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from opencompany.agents.runner import run_persona
from opencompany.models.db import Persona
from opencompany.models.engine import async_session

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _run_observer(persona_id: str, watch: dict):
    """Run an observer persona for a specific watch config."""
    async with async_session() as session:
        persona = await session.get(Persona, persona_id)
        if not persona or persona.status != "active":
            return

    source = watch.get("source", "unknown")
    path = watch.get("path", ".")
    task = f"Scan {source} at {path}. Find issues and create tickets for anything noteworthy."

    logger.info(f"Running observer {persona_id}: {task}")
    try:
        result = await run_persona(persona, task)
        logger.info(f"Observer {persona_id} finished: {result[:200]}")
    except Exception as e:
        logger.error(f"Observer {persona_id} failed: {e}")


def _parse_schedule(schedule_str: str) -> dict:
    """Parse schedule string like 'every 6h' or 'every 30m' to APScheduler kwargs."""
    s = schedule_str.lower().strip()
    if s.startswith("every "):
        val = s[6:]
        if val.endswith("h"):
            return {"trigger": "interval", "hours": int(val[:-1])}
        elif val.endswith("m"):
            return {"trigger": "interval", "minutes": int(val[:-1])}
        elif val.endswith("d"):
            return {"trigger": "interval", "days": int(val[:-1])}
    return {"trigger": "interval", "hours": 1}


async def register_observers():
    """Load all active observer personas and register their cron jobs."""
    async with async_session() as session:
        q = select(Persona).where(Persona.type == "observer", Persona.status == "active")
        result = await session.execute(q)
        observers = result.scalars().all()

    for persona in observers:
        for watch in persona.watches:
            schedule = watch.get("schedule", "every 1h")
            kwargs = _parse_schedule(schedule)
            job_id = f"{persona.id}:{watch.get('source', 'default')}"
            scheduler.add_job(
                _run_observer,
                id=job_id,
                replace_existing=True,
                args=[persona.id, watch],
                **kwargs,
            )
            logger.info(f"Scheduled observer {job_id} ({schedule})")


def start_scheduler():
    scheduler.start()
