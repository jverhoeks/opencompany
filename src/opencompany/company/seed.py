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
        logger.warning(f"No config at {config_path}, skipping seed")
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
    async with async_session() as session:
        for p in config.get("personas", []):
            if not valid_id.match(p["id"]):
                logger.warning(f"Skipping persona with invalid id: {p['id']!r}")
                continue
            persona = Persona(
                id=p["id"],
                name=p["name"],
                role=p["role"],
                type=p["type"],
                reports_to=p.get("reports_to"),
                skills=p.get("skills", []),
                watches=p.get("watches", []),
                picks_up=p.get("picks_up", []),
                tools=p.get("tools", []),
                backstory=p.get("backstory", ""),
            )
            session.add(persona)
            os.makedirs(os.path.join("workspaces", p["id"]), exist_ok=True)
            logger.info(f"Seeded persona: {p['name']} ({p['id']})")

        await session.commit()

    logger.info(f"Seeded {len(config.get('personas', []))} personas")
