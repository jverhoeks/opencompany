"""Persona management: CRUD, org chart, sync wrappers for tool use."""

import logging
import os
import re

from sqlalchemy import select

from opencompany.models.db import Persona
from opencompany.models.engine import async_session
from opencompany.utils import _run_async

logger = logging.getLogger(__name__)


_VALID_PERSONA_ID = re.compile(r"^[a-zA-Z0-9_-]+$")


async def _hire_persona(
    persona_id: str,
    name: str,
    role: str,
    persona_type: str,
    skills: list[str],
    backstory: str,
    reports_to: str | None = None,
) -> str:
    if not _VALID_PERSONA_ID.match(persona_id):
        return (
            f"Error: invalid persona_id {persona_id!r} (alphanumeric, hyphens, underscores only)"
        )
    async with async_session() as session:
        existing = await session.get(Persona, persona_id)
        if existing:
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

    logger.info("Hired persona %s (%s)", persona_id, role)
    return f"Hired {name} as {role} (id={persona_id})"


def hire_persona_sync(**kwargs) -> str:
    return _run_async(_hire_persona(**kwargs))


async def _fire_persona(persona_id: str, reason: str = "") -> str:
    async with async_session() as session:
        persona = await session.get(Persona, persona_id)
        if not persona:
            return f"Error: persona '{persona_id}' not found"
        persona.status = "terminated"
        await session.commit()
        return f"Terminated {persona.name} ({persona_id}). Reason: {reason}"


def fire_persona_sync(**kwargs) -> str:
    return _run_async(_fire_persona(**kwargs))


async def _list_personas(reports_to: str | None = None) -> list[dict]:
    async with async_session() as session:
        q = select(Persona).where(Persona.status == "active")
        if reports_to:
            q = q.where(Persona.reports_to == reports_to)
        result = await session.execute(q)
        return [
            {"id": p.id, "name": p.name, "role": p.role, "type": p.type, "skills": p.skills}
            for p in result.scalars().all()
        ]


def list_personas_sync(**kwargs) -> list[dict]:
    return _run_async(_list_personas(**kwargs))
