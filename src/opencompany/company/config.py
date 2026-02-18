"""Company config: load and query roles, org styles, personas from YAML."""

import logging
import os
from dataclasses import dataclass, field
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class CompanyConfig:
    """Parsed company configuration."""

    org_style: str
    org_styles: dict[str, dict[str, Any]]
    roles: dict[str, dict[str, Any]]
    personas: dict[str, dict[str, Any]]
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


# Module-level cache
_cached_config: CompanyConfig | None = None
_cached_path: str | None = None
_cached_mtime: float = 0.0


def load_company_config(path: str | None = None) -> CompanyConfig:
    """Load and parse company.yaml. Caches by file mtime."""
    global _cached_config, _cached_path, _cached_mtime

    if path is None:
        path = os.path.join("config", "company.yaml")

    if not os.path.isfile(path):
        raise FileNotFoundError(f"Company config not found: {path}")

    mtime = os.path.getmtime(path)
    if _cached_config and _cached_path == path and _cached_mtime == mtime:
        return _cached_config

    with open(path) as f:
        raw = yaml.safe_load(f)

    config = CompanyConfig(
        org_style=raw.get("org_style", "hierarchical"),
        org_styles=raw.get("org_styles", {}),
        roles=raw.get("roles", {}),
        personas=raw.get("personas", {}) or {},
        raw=raw,
    )

    _cached_config = config
    _cached_path = path
    _cached_mtime = mtime
    logger.info(
        "Loaded company config: %d roles, %d personas, org_style=%s",
        len(config.roles),
        len(config.personas),
        config.org_style,
    )
    return config


def get_role(role_id: str, config: CompanyConfig | None = None) -> dict[str, Any]:
    """Get a role definition by ID. Raises KeyError if not found."""
    if config is None:
        config = load_company_config()
    if role_id not in config.roles:
        raise KeyError(f"Role '{role_id}' not found in config")
    return config.roles[role_id]


def get_org_routing(config: CompanyConfig | None = None) -> dict[str, str]:
    """Get routing rules for the active org style."""
    if config is None:
        config = load_company_config()
    style = config.org_styles.get(config.org_style, {})
    return style.get("routing", {})


def invalidate_cache() -> None:
    """Clear the config cache (useful after writing new roles)."""
    global _cached_config, _cached_path, _cached_mtime
    _cached_config = None
    _cached_path = None
    _cached_mtime = 0.0


def add_role(
    role_id: str,
    role_type: str,
    responsibilities: str,
    constraints: str = "",
    tools: list[str] | None = None,
    tag_match: list[str] | None = None,
    routes_to: str | None = None,
    path: str | None = None,
) -> None:
    """Add a new role to company.yaml and invalidate the cache.

    Raises ValueError if the role already exists.
    """
    if path is None:
        path = os.path.join("config", "company.yaml")

    with open(path) as f:
        raw = yaml.safe_load(f)

    roles = raw.setdefault("roles", {})
    if role_id in roles:
        raise ValueError(f"Role '{role_id}' already exists")

    role_def: dict[str, Any] = {
        "type": role_type,
        "responsibilities": responsibilities,
    }
    if constraints:
        role_def["constraints"] = constraints
    if tools:
        role_def["tools"] = tools
    if tag_match:
        role_def["tag_match"] = tag_match
    if routes_to:
        role_def["routes_to"] = routes_to

    roles[role_id] = role_def

    with open(path, "w") as f:
        yaml.dump(raw, f, default_flow_style=False, sort_keys=False)

    invalidate_cache()
    logger.info("Added role '%s' to %s", role_id, path)
