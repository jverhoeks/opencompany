"""SoulManager: read, version, validate, apply, and rollback soul.md."""

import difflib
import logging
import re
from pathlib import Path

from opencompany.models.engine import async_session

logger = logging.getLogger(__name__)

_SOUL_PATH = Path("soul.md")
_MAX_LINES = 200
_MAX_RULES_PER_UPDATE = 3
_PROTECTED_PHRASES = [
    "This document may be updated",
    "No more than 3 rules may change",
    "Protected rules cannot be removed",
    "soul.md must not exceed 200 lines",
]


def read_soul() -> str:
    """Read current soul.md content."""
    if not _SOUL_PATH.exists():
        return ""
    return _SOUL_PATH.read_text()


def _get_version_from_content(content: str) -> int:
    """Extract version number from soul.md header."""
    match = re.search(r"^# Version:\s*(\d+)", content, re.MULTILINE)
    return int(match.group(1)) if match else 0


def _count_rule_changes(old: str, new: str) -> int:
    """Count number of rule lines that differ between old and new."""
    old_rules = {line.strip() for line in old.splitlines() if re.match(r"^\d+\.\s", line.strip())}
    new_rules = {line.strip() for line in new.splitlines() if re.match(r"^\d+\.\s", line.strip())}
    return len(old_rules.symmetric_difference(new_rules))


def _protected_rules_intact(new_content: str) -> bool:
    """Check that all protected phrases are present in the new content."""
    return all(phrase in new_content for phrase in _PROTECTED_PHRASES)


def validate_soul_update(current: str, proposed: str) -> tuple[bool, str]:
    """Validate a proposed soul.md update against safety gates.

    Returns (valid, reason).
    """
    # Gate 1: version must be incremented
    old_ver = _get_version_from_content(current)
    new_ver = _get_version_from_content(proposed)
    if new_ver <= old_ver:
        return False, f"Version must be incremented (current={old_ver}, proposed={new_ver})"

    # Gate 2: max rule changes
    changes = _count_rule_changes(current, proposed)
    if changes > _MAX_RULES_PER_UPDATE:
        return False, f"Too many rule changes ({changes} > {_MAX_RULES_PER_UPDATE})"

    # Gate 3: protected rules intact
    if not _protected_rules_intact(proposed):
        return False, "Protected rules must not be removed"

    # Gate 4: line limit
    lines = len(proposed.splitlines())
    if lines > _MAX_LINES:
        return False, f"soul.md exceeds {_MAX_LINES} lines ({lines})"

    return True, "ok"


async def propose_update(proposed: str, rationale: str, proposed_by: str) -> tuple[bool, str]:
    """Propose a soul.md update. Validates, applies if valid, persists version.

    Returns (accepted, reason).
    """

    from opencompany.models.db import SoulVersion

    current = read_soul()
    valid, reason = validate_soul_update(current, proposed)
    if not valid:
        logger.warning("Soul update rejected from %s: %s", proposed_by, reason)
        return False, reason

    # Generate diff
    diff = "\n".join(
        difflib.unified_diff(
            current.splitlines(),
            proposed.splitlines(),
            fromfile="soul.md (old)",
            tofile="soul.md (new)",
            lineterm="",
        )
    )

    # Apply
    _SOUL_PATH.write_text(proposed)

    # Persist version
    new_ver = _get_version_from_content(proposed)
    async with async_session() as session:
        session.add(
            SoulVersion(
                version=new_ver,
                content=proposed,
                diff=diff,
                rationale=rationale,
                proposed_by=proposed_by,
            )
        )
        await session.commit()

    logger.info("Soul v%d applied (by %s): %s", new_ver, proposed_by, rationale)
    return True, f"Soul v{new_ver} applied"


async def rollback(target_version: int) -> tuple[bool, str]:
    """Rollback soul.md to a specific version."""
    from sqlalchemy import select

    from opencompany.models.db import SoulVersion

    async with async_session() as session:
        result = await session.execute(
            select(SoulVersion).where(SoulVersion.version == target_version)
        )
        sv = result.scalars().first()
        if not sv:
            return False, f"Version {target_version} not found"

        _SOUL_PATH.write_text(sv.content)
        logger.info("Soul rolled back to v%d", target_version)
        return True, f"Rolled back to v{target_version}"
