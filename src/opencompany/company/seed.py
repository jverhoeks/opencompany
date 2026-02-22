import logging
import os
import re

import yaml
from sqlalchemy import select

from opencompany.models.db import Persona
from opencompany.models.engine import async_session

logger = logging.getLogger(__name__)


async def seed_company(config_path: str = "config/company.yaml"):
    """Load initial personas from company.yaml if DB is empty."""
    if not os.path.isfile(config_path):
        logger.warning("No config at %s, skipping seed", config_path)
        return

    async with async_session() as session:
        result = await session.execute(select(Persona).limit(1))
        if result.scalars().first():
            logger.info("Personas already exist, skipping seed")
            return

    with open(config_path) as f:
        try:
            config = yaml.safe_load(f)
        except yaml.YAMLError:
            logger.exception("Failed to parse %s", config_path)
            return

    valid_id = re.compile(r"^[a-zA-Z0-9_-]+$")
    roles = config.get("roles", {})
    personas_config = config.get("personas", {})

    # New format: personas is a dict referencing roles
    if isinstance(personas_config, dict):
        persona_list = _build_persona_list_from_dict(personas_config, roles)
    # Old format: personas is a list of full persona defs
    elif isinstance(personas_config, list):
        persona_list = personas_config
    else:
        persona_list = []

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


def _build_persona_list_from_dict(personas: dict, roles: dict) -> list[dict]:
    """Convert new-format personas dict to list, merging role config."""
    result = []
    for persona_id, pdata in personas.items():
        role_id = pdata.get("role", persona_id)
        role_config = roles.get(role_id, {})
        result.append(
            {
                "id": persona_id,
                "name": pdata.get("name", persona_id),
                "role": role_id.replace("-", " ").title(),
                "type": role_config.get("type", "solver"),
                "skills": role_config.get("tag_match", []),
                "tools": role_config.get("tools", []),
                "picks_up": role_config.get("tag_match", []),
                "reports_to": pdata.get("reports_to"),
                "model_id": role_config.get("model"),
                "daily_token_budget": role_config.get("daily_token_budget", 0),
                "backstory": pdata.get("backstory", ""),
            }
        )
    return result
