import logging
import os
import re

from sqlalchemy import select

from opencompany.company.config import load_company_config
from opencompany.models.db import Persona
from opencompany.models.engine import async_session

logger = logging.getLogger(__name__)


async def seed_company(config_path: str = "config/company.yaml"):
    """Load initial personas from company.yaml if DB is empty.

    Builtin personas (roles with ``builtin: true``) are always ensured to
    exist and be active, even when the DB already contains other personas.
    """
    try:
        company_config = load_company_config(config_path)
    except FileNotFoundError:
        logger.warning("No config at %s, skipping seed", config_path)
        return
    except ValueError:
        # load_company_config already logged the detailed parse error
        return

    valid_id = re.compile(r"^[a-zA-Z0-9_-]+$")
    roles = company_config.roles
    personas_config = company_config.personas

    default_model = company_config.default_model

    # New format: personas is a dict referencing roles
    if isinstance(personas_config, dict):
        persona_list = _build_persona_list_from_dict(personas_config, roles, default_model)
    # Old format: personas is a list of full persona defs
    elif isinstance(personas_config, list):
        persona_list = personas_config
    else:
        persona_list = []

    # Auto-add builtin roles that aren't already listed in personas
    listed_role_ids = {p.get("role_id", p.get("id", "")) for p in persona_list}
    for role_id, role_cfg in roles.items():
        if role_cfg.get("builtin") and role_id not in listed_role_ids:
            persona_list.append(
                {
                    "id": role_id,
                    "name": role_id.upper()
                    if len(role_id) <= 3
                    else role_id.replace("-", " ").title(),
                    "role": role_id.replace("-", " ").title(),
                    "role_id": role_id,
                    "type": role_cfg.get("type", "manager"),
                    "skills": role_cfg.get("tag_match", []),
                    "tools": role_cfg.get("tools", []),
                    "picks_up": role_cfg.get("tag_match", []),
                    "reports_to": None,
                    "model_id": role_cfg.get("model") or default_model or None,
                    "daily_token_budget": role_cfg.get("daily_token_budget", 0),
                    "backstory": "",
                }
            )
            logger.info("Auto-adding builtin role as persona: %s", role_id)

    # Determine which persona IDs are builtin (role has builtin: true)
    builtin_ids = set()
    for p in persona_list:
        role_id = p.get("role_id", p.get("id", ""))
        if roles.get(role_id, {}).get("builtin"):
            builtin_ids.add(p["id"])

    async with async_session() as session:
        result = await session.execute(select(Persona).limit(1))
        db_has_personas = result.scalars().first() is not None

    if db_has_personas:
        logger.info("Personas already exist, ensuring builtins are active")
        await _ensure_builtins(persona_list, builtin_ids)
        return

    async with async_session() as session:
        for p in persona_list:
            pid = p.get("id", "")
            if not valid_id.match(pid):
                logger.warning("Skipping persona with invalid id: %r", pid)
                continue
            persona = Persona(
                id=pid,
                name=p["name"],
                role=p["role"],
                type=p["type"],
                reports_to=p.get("reports_to"),
                skills=p.get("skills", []),
                watches=p.get("watches", []),
                picks_up=p.get("picks_up", []),
                tools=p.get("tools", []),
                model_id=p.get("model_id"),
                daily_token_budget=p.get("daily_token_budget", 0),
                backstory=p.get("backstory", ""),
            )
            session.add(persona)
            os.makedirs(os.path.join("workspaces", pid), exist_ok=True)
            logger.info("Seeded persona: %s (%s)", p["name"], pid)

        await session.commit()

    logger.info("Seeded %d personas", len(persona_list))


async def _ensure_builtins(persona_list: list[dict], builtin_ids: set[str]) -> None:
    """Create or reactivate builtin personas so they are always present."""
    if not builtin_ids:
        return

    async with async_session() as session:
        for p in persona_list:
            pid = p.get("id", "")
            if pid not in builtin_ids:
                continue

            existing = await session.get(Persona, pid)
            if existing:
                if existing.status != "active":
                    existing.status = "active"
                    logger.info("Reactivated builtin persona: %s", pid)
            else:
                persona = Persona(
                    id=pid,
                    name=p["name"],
                    role=p["role"],
                    type=p["type"],
                    reports_to=p.get("reports_to"),
                    skills=p.get("skills", []),
                    watches=p.get("watches", []),
                    picks_up=p.get("picks_up", []),
                    tools=p.get("tools", []),
                    model_id=p.get("model_id"),
                    daily_token_budget=p.get("daily_token_budget", 0),
                    backstory=p.get("backstory", ""),
                )
                session.add(persona)
                os.makedirs(os.path.join("workspaces", pid), exist_ok=True)
                logger.info("Created missing builtin persona: %s", pid)

        await session.commit()


def _build_persona_list_from_dict(
    personas: dict, roles: dict, default_model: str = ""
) -> list[dict]:
    """Convert new-format personas dict to list, merging role config."""
    result = []
    for persona_id, pdata in personas.items():
        role_id = pdata.get("role", persona_id)
        role_config = roles.get(role_id, {})
        model_id = role_config.get("model") or default_model or None
        result.append(
            {
                "id": persona_id,
                "name": pdata.get("name", persona_id),
                "role": role_id.replace("-", " ").title(),
                "role_id": role_id,
                "type": role_config.get("type", "solver"),
                "skills": role_config.get("tag_match", []),
                "tools": role_config.get("tools", []),
                "picks_up": role_config.get("tag_match", []),
                "reports_to": pdata.get("reports_to"),
                "model_id": model_id,
                "daily_token_budget": role_config.get("daily_token_budget", 0),
                "backstory": pdata.get("backstory", ""),
            }
        )
    return result
