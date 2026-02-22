"""Trust tier system: role-based tool access control for personas."""

import logging

from opencompany.models.db import Persona

logger = logging.getLogger(__name__)

# Tier levels — higher number = more access
TIERS = {"external": 0, "solver": 1, "lead": 2, "full": 3}

# Minimum tier required to use each tool. Tools not listed default to "external" (anyone).
TOOL_TIER_REQUIREMENTS: dict[str, str] = {
    # Full tier only (CEO, HR)
    "hire_persona": "full",
    "fire_persona": "full",
    "create_role": "full",
    "contact_overseer": "lead",
    # Lead tier+
    "create_ticket": "lead",
    "send_message": "lead",
    # Solver tier+
    "write_file": "solver",
    "update_ticket": "solver",
    "web_fetch": "solver",
    # Everything else (read_file, list_files, grep_code, list_tickets,
    # list_team, web_search, remember, recall) is accessible at external tier.
}


def get_trust_tier(persona: Persona) -> str:
    """Derive trust tier from persona type and ID."""
    # CEO and HR always get full access
    if persona.id in ("ceo", "hr"):
        return "full"
    if persona.type == "manager":
        return "full"
    if persona.type == "lead":
        return "lead"
    if persona.type == "solver":
        return "solver"
    return "external"


def filter_tools_by_tier(tool_names: list[str], tier: str) -> tuple[list[str], list[str]]:
    """Filter tool names by trust tier.

    Returns (allowed, denied) lists. Logs each denial.
    """
    tier_level = TIERS.get(tier, 0)
    allowed = []
    denied = []

    for name in tool_names:
        required_tier = TOOL_TIER_REQUIREMENTS.get(name, "external")
        required_level = TIERS.get(required_tier, 0)
        if tier_level >= required_level:
            allowed.append(name)
        else:
            denied.append(name)
            logger.warning(
                "Trust tier %r (level %d) denied tool %r (requires %r, level %d)",
                tier,
                tier_level,
                name,
                required_tier,
                required_level,
            )

    return allowed, denied
