"""Persona management: CRUD, org chart, sync wrappers for tool use."""

import logging
import os
import re

import yaml
from sqlalchemy import func, select

from opencompany.models.db import Persona, Ticket
from opencompany.models.engine import async_session
from opencompany.utils import _run_async

logger = logging.getLogger(__name__)


_VALID_PERSONA_ID = re.compile(r"^[a-zA-Z0-9_-]+$")
_DEFAULT_MAX_HEADCOUNT = 2  # max active personas per role unless overridden
_MAX_TEAM_SIZE = int(os.environ.get("MAX_TEAM_SIZE", "12"))
_HIRE_CAPACITY_THRESHOLD = 1.5  # only hire when open_tickets / active_solvers >= this


async def capacity_ratio() -> float:
    """Return open_tickets / active_solvers. Values >1.5 suggest understaffing.

    Returns float('inf') when there are no active solvers (always hire).
    """
    async with async_session() as session:
        open_result = await session.execute(
            select(func.count(Ticket.id)).where(Ticket.status == "open")
        )
        open_count = open_result.scalar() or 0

        solver_result = await session.execute(
            select(func.count(Persona.id)).where(
                Persona.type == "solver",
                Persona.status == "active",
            )
        )
        solver_count = solver_result.scalar() or 0

    if solver_count == 0:
        return float("inf")  # no solvers = always understaffed
    return open_count / solver_count


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

    # Duplicate check — fast fail before capacity checks
    async with async_session() as session:
        existing = await session.get(Persona, persona_id)
        if existing:
            logger.warning("Hire rejected: persona %r already exists", persona_id)
            return f"Error: persona '{persona_id}' already exists"

    # Global team size cap
    async with async_session() as session:
        total_result = await session.execute(
            select(func.count(Persona.id)).where(Persona.status == "active")
        )
        total_active = total_result.scalar() or 0
    if total_active >= _MAX_TEAM_SIZE:
        logger.warning(
            "Hire rejected: team size %d already at cap %d",
            total_active,
            _MAX_TEAM_SIZE,
        )
        return (
            f"Error: team already has {total_active} active personas "
            f"(max {_MAX_TEAM_SIZE}). Fire someone first."
        )

    # Capacity ratio check — don't hire if team already has sufficient capacity
    ratio = await capacity_ratio()
    if ratio < _HIRE_CAPACITY_THRESHOLD:
        logger.warning(
            "Hire rejected: capacity ratio %.1f < %.1f (team has sufficient capacity)",
            ratio,
            _HIRE_CAPACITY_THRESHOLD,
        )
        return (
            f"Hiring rejected: team has sufficient capacity "
            f"(ratio={ratio:.1f}, threshold={_HIRE_CAPACITY_THRESHOLD}). "
            f"No hire needed."
        )

    # Auto-fill picks_up, tools, model_id, budget from role config when not provided
    role_id = role.lower().replace(" ", "-")
    model_id = None
    daily_token_budget = 0
    max_headcount = _DEFAULT_MAX_HEADCOUNT
    try:
        from opencompany.company.config import load_company_config

        config = load_company_config()
        role_config = config.roles.get(role_id, {})
        if not picks_up:
            picks_up = role_config.get("tag_match", [])
        if not tools:
            tools = role_config.get("tools", [])
        model_id = role_config.get("model")
        daily_token_budget = role_config.get("daily_token_budget", 0)
        max_headcount = role_config.get("max_headcount", _DEFAULT_MAX_HEADCOUNT)
    except Exception:
        logger.debug("Could not load role config for %s, using provided values", role_id)

    async with async_session() as session:
        # Headcount guard: reject if too many active personas in same role
        result = await session.execute(
            select(func.count(Persona.id)).where(
                Persona.role == role_id,
                Persona.status == "active",
            )
        )
        current_count = result.scalar() or 0
        if current_count >= max_headcount:
            logger.warning(
                "Hire rejected: role %r already has %d/%d active personas",
                role_id,
                current_count,
                max_headcount,
            )
            return (
                f"Error: role '{role}' already has {current_count} active "
                f"persona(s) (max {max_headcount}). Fire someone first or "
                f"increase max_headcount in the role config."
            )

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
            model_id=model_id,
            daily_token_budget=daily_token_budget,
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

    # Sweep unassigned tickets — the new hire might match orphaned work
    try:
        from opencompany.company.engine import sweep_unassigned_tickets

        swept = await sweep_unassigned_tickets()
        if swept:
            logger.info("Post-hire sweep routed %d tickets after hiring %s", swept, persona_id)
    except Exception:
        logger.debug("Post-hire sweep skipped (engine not ready)")

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
