"""Company config: load and query roles, org styles, personas from YAML."""

import contextlib
import logging
import os
import tempfile
from collections.abc import Iterator
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
    default_model: str = ""
    model_provider: str = ""
    bedrock_region: str = ""
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
        try:
            raw = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            # Extract line info from YAML parse errors for actionable messages
            msg = f"Failed to parse {path}"
            if hasattr(exc, "problem_mark") and exc.problem_mark:
                mark = exc.problem_mark
                msg += f" at line {mark.line + 1}, column {mark.column + 1}"
            if hasattr(exc, "problem") and exc.problem:
                msg += f": {exc.problem}"
            logger.error(msg)
            raise ValueError(msg) from exc

    if not isinstance(raw, dict):
        msg = f"{path} is not a valid YAML mapping (got {type(raw).__name__})"
        logger.error(msg)
        raise ValueError(msg)

    # Validate required top-level keys
    missing = {"roles", "personas"} - set(raw.keys())
    if missing:
        msg = f"{path} missing required keys: {', '.join(sorted(missing))}"
        logger.error(msg)
        raise ValueError(msg)

    config = CompanyConfig(
        org_style=raw.get("org_style", "hierarchical"),
        org_styles=raw.get("org_styles", {}),
        roles=raw.get("roles", {}),
        personas=raw.get("personas", {}) or {},
        default_model=raw.get("default_model", ""),
        model_provider=raw.get("model_provider", ""),
        bedrock_region=raw.get("bedrock_region", ""),
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


async def boot_persona_configs(yaml_path: str | None = None) -> int:
    """Seed PersonaConfig table from company.yaml on first start.

    Skips if DB already has persona configs (i.e. company is already running).
    Returns the number of configs seeded.
    """
    from sqlalchemy import func, select

    from opencompany.models.db import PersonaConfig
    from opencompany.models.engine import async_session

    async with async_session() as session:
        count = await session.scalar(select(func.count(PersonaConfig.id)))
        if count and count > 0:
            logger.info("PersonaConfig already seeded (%d entries), skipping", count)
            return 0

    config = load_company_config(yaml_path)

    seeded = 0
    async with async_session() as session:
        for role_id, role_data in config.roles.items():
            pc = PersonaConfig(
                id=role_id,
                name=role_data.get("name", role_id),
                role=role_id,
                trust=_trust_from_type(role_data.get("type", "solver")),
                skills=role_data.get("tag_match", []),
                budget_tokens_daily=role_data.get("daily_token_budget", 0),
                instructions=role_data.get("responsibilities", ""),
                personality=role_data.get("personality", {}),
                updated_by="system",
            )
            session.add(pc)
            seeded += 1
        await session.commit()

    logger.info("Seeded %d persona configs from YAML", seeded)
    return seeded


def _trust_from_type(role_type: str) -> str:
    """Map role type to trust tier."""
    return {
        "manager": "full",
        "lead": "lead",
        "solver": "solver",
        "observer": "external",
    }.get(role_type, "solver")


@contextlib.contextmanager
def _locked_yaml_edit(path: str) -> Iterator[dict]:
    """Read-modify-write ``path`` atomically with a cross-process file lock.

    Yields the parsed YAML dict; whatever the caller mutates is written back
    on clean exit. The write is atomic (tmpfile + fsync + rename) and guarded
    by ``fcntl.flock`` so concurrent agent writes can't interleave and lose
    each other's changes.
    """
    import fcntl

    dirpath = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(dirpath, exist_ok=True)
    lock_path = f"{path}.lock"
    # Use O_CREAT so the lockfile exists on first use; keep it around across
    # calls so flock contention works across processes.
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        with open(path) as f:
            raw = yaml.safe_load(f) or {}

        yield raw

        # Write to a temp file in the same directory, then atomic rename.
        fd, tmp_path = tempfile.mkstemp(
            prefix=f".{os.path.basename(path)}.", suffix=".tmp", dir=dirpath
        )
        try:
            with os.fdopen(fd, "w") as tmp_f:
                yaml.dump(raw, tmp_f, default_flow_style=False, sort_keys=False)
                tmp_f.flush()
                os.fsync(tmp_f.fileno())
            os.replace(tmp_path, path)
        except Exception:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(tmp_path)
            raise
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)


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

    with _locked_yaml_edit(path) as raw:
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

    invalidate_cache()
    logger.info("Added role '%s' to %s", role_id, path)


def update_role(
    role_id: str,
    updates: dict[str, Any],
    path: str | None = None,
) -> None:
    """Update an existing role in company.yaml. Raises KeyError if not found."""
    if path is None:
        path = os.path.join("config", "company.yaml")

    with _locked_yaml_edit(path) as raw:
        roles = raw.get("roles", {})
        if role_id not in roles:
            raise KeyError(f"Role '{role_id}' not found")
        roles[role_id].update(updates)

    invalidate_cache()
    logger.info("Updated role '%s' in %s", role_id, path)


def delete_role(role_id: str, path: str | None = None) -> None:
    """Delete a role from company.yaml. Raises KeyError if not found."""
    if path is None:
        path = os.path.join("config", "company.yaml")

    with _locked_yaml_edit(path) as raw:
        roles = raw.get("roles", {})
        if role_id not in roles:
            raise KeyError(f"Role '{role_id}' not found")
        del roles[role_id]

    invalidate_cache()
    logger.info("Deleted role '%s' from %s", role_id, path)
