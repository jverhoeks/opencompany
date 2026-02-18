"""Persona management: CRUD, org chart, sync wrappers for tool use."""

import logging
import os
import re

import yaml
from sqlalchemy import select

from opencompany.models.db import Persona, Ticket
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
    tools: list[str] | None = None,
    picks_up: list[str] | None = None,
) -> str:
    if not _VALID_PERSONA_ID.match(persona_id):
        return (
            f"Error: invalid persona_id {persona_id!r} (alphanumeric, hyphens, underscores only)"
        )
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
            tools=tools or [],
            picks_up=picks_up or [],
        )
        session.add(persona)
        await session.commit()

    workspace = os.path.join("workspaces", persona_id)
    os.makedirs(workspace, exist_ok=True)

    # Sync to company.yaml
    _append_to_company_yaml(
        persona_id,
        name,
        role,
        persona_type,
        skills,
        backstory,
        reports_to,
        tools,
        picks_up,
    )

    logger.info("Hired persona %s (%s) as %s", persona_id, name, role)
    return f"Hired {name} as {role} (id={persona_id})"


def _append_to_company_yaml(
    persona_id: str,
    name: str,
    role: str,
    persona_type: str,
    skills: list[str],
    backstory: str,
    reports_to: str | None,
    tools: list[str] | None,
    picks_up: list[str] | None,
) -> None:
    """Add a new persona entry to config/company.yaml (dict format)."""
    yaml_path = os.path.join("config", "company.yaml")
    if not os.path.exists(yaml_path):
        return

    try:
        with open(yaml_path) as f:
            raw = yaml.safe_load(f)

        personas = raw.setdefault("personas", {})
        if persona_id in personas:
            logger.warning("Persona %s already in YAML, skipping", persona_id)
            return

        # Role ID is derived from the role title
        role_id = role.lower().replace(" ", "-")
        entry: dict = {"role": role_id, "name": name, "backstory": backstory}
        if reports_to:
            entry["reports_to"] = reports_to

        personas[persona_id] = entry

        with open(yaml_path, "w") as f:
            yaml.dump(raw, f, default_flow_style=False, sort_keys=False)

        from opencompany.company.config import invalidate_cache

        invalidate_cache()
        logger.info("Added persona %s to company.yaml", persona_id)
    except Exception:
        logger.exception("Failed to update company.yaml for persona %s", persona_id)


def hire_persona_sync(**kwargs) -> str:
    return _run_async(_hire_persona(**kwargs))


async def _fire_persona(persona_id: str, reason: str = "") -> str:
    async with async_session() as session:
        persona = await session.get(Persona, persona_id)
        if not persona:
            logger.warning("Fire rejected: persona %r not found", persona_id)
            return f"Error: persona '{persona_id}' not found"
        persona.status = "fired"

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
                "Reassigned %d orphaned tickets from fired persona %s",
                orphan_count,
                persona_id,
            )
        logger.info("Fired persona %s (%s). Reason: %s", persona_id, persona.name, reason)
        return f"Fired {persona.name} ({persona_id}). Reason: {reason}"


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
