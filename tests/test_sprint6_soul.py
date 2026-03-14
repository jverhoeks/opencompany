"""Tests for Sprint 6: soul.md self-improvement system (SI1-SI3)."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from opencompany.company.soul import (
    _count_rule_changes,
    _get_version_from_content,
    _protected_rules_intact,
    propose_update,
    rollback,
    validate_soul_update,
)
from opencompany.models.db import SoulVersion


@pytest.fixture
async def factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class TestSoulHelpers:
    def test_get_version_from_content(self):
        assert _get_version_from_content("# Version: 3\nstuff") == 3
        assert _get_version_from_content("no version here") == 0

    def test_count_rule_changes(self):
        old = "1. Rule A\n2. Rule B\n3. Rule C"
        new = "1. Rule A\n2. Rule B modified\n3. Rule C"
        assert _count_rule_changes(old, new) == 2  # B changed (old B + new B)

    def test_protected_rules_intact(self):
        content = (
            "This document may be updated\n"
            "No more than 3 rules may change\n"
            "Protected rules cannot be removed\n"
            "soul.md must not exceed 200 lines\n"
        )
        assert _protected_rules_intact(content) is True
        assert _protected_rules_intact("missing stuff") is False


# ---------------------------------------------------------------------------
# Validation gates
# ---------------------------------------------------------------------------
class TestValidation:
    def test_rejects_same_version(self):
        current = "# Version: 1\n1. Rule A"
        proposed = "# Version: 1\n1. Rule B"
        valid, reason = validate_soul_update(current, proposed)
        assert valid is False
        assert "incremented" in reason

    def test_rejects_too_many_changes(self):
        current = "# Version: 1\n1. A\n2. B\n3. C\n4. D\n"
        proposed = (
            "# Version: 2\n1. X\n2. Y\n3. Z\n4. W\n"
            "This document may be updated\n"
            "No more than 3 rules may change\n"
            "Protected rules cannot be removed\n"
            "soul.md must not exceed 200 lines\n"
        )
        valid, reason = validate_soul_update(current, proposed)
        assert valid is False
        assert "Too many" in reason

    def test_rejects_missing_protected_rules(self):
        current = (
            "# Version: 1\n1. A\n"
            "This document may be updated\n"
            "No more than 3 rules may change\n"
            "Protected rules cannot be removed\n"
            "soul.md must not exceed 200 lines\n"
        )
        proposed = "# Version: 2\n1. A modified\n"
        valid, reason = validate_soul_update(current, proposed)
        assert valid is False
        assert "Protected" in reason

    def test_rejects_too_many_lines(self):
        current = "# Version: 1\n1. A\n"
        proposed = (
            "# Version: 2\n1. A modified\n"
            "This document may be updated\n"
            "No more than 3 rules may change\n"
            "Protected rules cannot be removed\n"
            "soul.md must not exceed 200 lines\n" + "\n".join(f"Line {i}" for i in range(200))
        )
        valid, reason = validate_soul_update(current, proposed)
        assert valid is False
        assert "200 lines" in reason

    def test_accepts_valid_update(self):
        current = (
            "# Version: 1\n1. Old rule\n"
            "This document may be updated\n"
            "No more than 3 rules may change\n"
            "Protected rules cannot be removed\n"
            "soul.md must not exceed 200 lines\n"
        )
        proposed = (
            "# Version: 2\n1. New rule\n"
            "This document may be updated\n"
            "No more than 3 rules may change\n"
            "Protected rules cannot be removed\n"
            "soul.md must not exceed 200 lines\n"
        )
        valid, reason = validate_soul_update(current, proposed)
        assert valid is True


# ---------------------------------------------------------------------------
# propose_update + rollback
# ---------------------------------------------------------------------------
class TestProposeAndRollback:
    async def test_propose_valid_update(self, factory, tmp_path):
        soul_file = tmp_path / "soul.md"
        current = (
            "# Version: 1\n1. Old rule\n"
            "This document may be updated\n"
            "No more than 3 rules may change\n"
            "Protected rules cannot be removed\n"
            "soul.md must not exceed 200 lines\n"
        )
        soul_file.write_text(current)

        proposed = (
            "# Version: 2\n1. New rule\n"
            "This document may be updated\n"
            "No more than 3 rules may change\n"
            "Protected rules cannot be removed\n"
            "soul.md must not exceed 200 lines\n"
        )

        with (
            patch("opencompany.company.soul._SOUL_PATH", soul_file),
            patch("opencompany.company.soul.async_session", factory),
        ):
            accepted, reason = await propose_update(proposed, "Modernize rules", "company-analyst")

        assert accepted is True
        assert "v2" in reason
        assert soul_file.read_text() == proposed

        # Check DB has the version
        async with factory() as session:
            result = await session.execute(select(SoulVersion))
            sv = result.scalars().first()
            assert sv.version == 2
            assert sv.proposed_by == "company-analyst"

    async def test_propose_invalid_rejected(self, factory, tmp_path):
        soul_file = tmp_path / "soul.md"
        soul_file.write_text("# Version: 1\n1. Rule\n")

        with (
            patch("opencompany.company.soul._SOUL_PATH", soul_file),
            patch("opencompany.company.soul.async_session", factory),
        ):
            accepted, reason = await propose_update(
                "# Version: 1\n1. Same version\n",  # no version bump
                "Bad update",
                "rogue-agent",
            )

        assert accepted is False
        assert "incremented" in reason

    async def test_rollback_to_version(self, factory, tmp_path):
        soul_file = tmp_path / "soul.md"
        soul_file.write_text("# Version: 2\nCurrent content")

        # Seed a v1 in the DB
        async with factory() as session:
            session.add(
                SoulVersion(
                    version=1,
                    content="# Version: 1\nOriginal content",
                    proposed_by="system",
                )
            )
            await session.commit()

        with (
            patch("opencompany.company.soul._SOUL_PATH", soul_file),
            patch("opencompany.company.soul.async_session", factory),
        ):
            ok, msg = await rollback(1)

        assert ok is True
        assert soul_file.read_text() == "# Version: 1\nOriginal content"

    async def test_rollback_nonexistent_version(self, factory):
        with patch("opencompany.company.soul.async_session", factory):
            ok, msg = await rollback(999)

        assert ok is False
        assert "not found" in msg


# ---------------------------------------------------------------------------
# Soul injection into prompts
# ---------------------------------------------------------------------------
class TestSoulPromptInjection:
    def test_soul_injected_into_prompt(self, tmp_path):
        soul_file = tmp_path / "soul.md"
        soul_file.write_text("# Company Soul\n1. Be excellent.")

        persona = MagicMock()
        persona.id = "dev-1"
        persona.name = "Dev"
        persona.role = "Developer"
        persona.type = "solver"
        persona.skills = ["python"]
        persona.tools = ["read_file"]
        persona.backstory = "A developer."

        with (
            patch("opencompany.company.soul._SOUL_PATH", soul_file),
            patch(
                "opencompany.agents.prompts._get_role_config",
                return_value={},
            ),
            patch(
                "opencompany.agents.prompts._build_personality_section",
                return_value="",
            ),
            patch(
                "opencompany.agents.prompts._build_policy_section",
                return_value="",
            ),
        ):
            from opencompany.agents.prompts import build_system_prompt

            prompt = build_system_prompt(persona)

        assert "COMPANY OPERATING PRINCIPLES" in prompt
        assert "Be excellent" in prompt
