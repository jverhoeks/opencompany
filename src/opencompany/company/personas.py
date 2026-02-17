"""Persona management: CRUD, org chart, sync wrappers for tool use."""

import asyncio
import logging
import os

from sqlalchemy import select

from opencompany.models.db import Persona, Ticket
from opencompany.models.engine import async_session, get_main_loop

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from a sync context (e.g. agent tools running in threads)."""
    loop = get_main_loop()
    if loop and loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=60)
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _hire_persona(
    persona_id: str,
    name: str,
    role: str,
    persona_type: str,
    skills: list[str],
    backstory: str,
    reports_to: str | None = None,
) -> str:
    async with async_session() as session:
        existing = await session.get(Persona, persona_id)
        if existing:
            logger.warning("Hire rejected: persona %r already exists", persona_id)
            return f"Error: persona '{persona_id}' already exists"

        persona = Persona(
            id=persona_id,
            name=name,
            role=role,
            type=persona_type,
            skills=skills,
            backstory=backstory,
            reports_to=reports_to,
        )
        session.add(persona)
        await session.commit()

    workspace = os.path.join("workspaces", persona_id)
    os.makedirs(workspace, exist_ok=True)

    logger.info("Hired persona %s (%s) as %s", persona_id, name, role)
    return f"Hired {name} as {role} (id={persona_id})"


def hire_persona_sync(**kwargs) -> str:
    return _run_async(_hire_persona(**kwargs))


async def _fire_persona(persona_id: str, reason: str = "") -> str:
    async with async_session() as session:
        persona = await session.get(Persona, persona_id)
        if not persona:
            logger.warning("Fire rejected: persona %r not found", persona_id)
            return f"Error: persona '{persona_id}' not found"
        persona.status = "terminated"

        # Reassign orphaned tickets back to the open pool
        orphaned = await session.execute(
            select(Ticket).where(
                Ticket.assigned_to == persona_id,
                Ticket.status.in_(("open", "assigned", "in_progress")),
            )
        )
        orphan_count = 0
        for ticket in orphaned.scalars().all():
            ticket.status = "open"
            ticket.assigned_to = None
            orphan_count += 1

        await session.commit()

        if orphan_count:
            logger.info(
                "Reassigned %d orphaned tickets from terminated persona %s",
                orphan_count,
                persona_id,
            )
        logger.info("Terminated persona %s (%s). Reason: %s", persona_id, persona.name, reason)
        return f"Terminated {persona.name} ({persona_id}). Reason: {reason}"


def fire_persona_sync(**kwargs) -> str:
    return _run_async(_fire_persona(**kwargs))


async def _list_personas(reports_to: str | None = None) -> list[dict]:
    async with async_session() as session:
        q = select(Persona).where(Persona.status == "active")
        if reports_to:
            q = q.where(Persona.reports_to == reports_to)
        result = await session.execute(q)
        personas = [
            {"id": p.id, "name": p.name, "role": p.role, "type": p.type, "skills": p.skills}
            for p in result.scalars().all()
        ]
        logger.debug("Listed %d active personas (reports_to=%s)", len(personas), reports_to)
        return personas


def list_personas_sync(**kwargs) -> list[dict]:
    return _run_async(_list_personas(**kwargs))
