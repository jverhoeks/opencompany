"""Tests for Sprint 9: S3 hiring guardrail + S6 Agent SOPs."""

from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from opencompany.agents.hooks import HiringGuardrail
from opencompany.agents.prompts import load_sop_for_tags
from opencompany.models.db import Persona, Ticket


@pytest.fixture
async def factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# S3: Hiring guardrail
# ---------------------------------------------------------------------------
class TestHiringGuardrail:
    async def test_allows_hire_when_understaffed(self, factory):
        """No steering message when capacity ratio >= 1.5."""
        async with factory() as session:
            session.add(Persona(id="s1", name="S", role="Dev", type="solver", backstory="x"))
            for i in range(3):
                session.add(Ticket(title=f"T{i}", tags=["x"], status="open"))
            await session.commit()

        guardrail = HiringGuardrail()
        with patch("opencompany.company.personas.async_session", factory):
            result = await guardrail.check_hire("hire_persona", {"name": "New"})

        assert result is None

    async def test_blocks_hire_when_sufficient(self, factory):
        """Returns steering message when capacity ratio < 1.5."""
        async with factory() as session:
            for i in range(3):
                session.add(
                    Persona(
                        id=f"s{i}",
                        name=f"S{i}",
                        role="Dev",
                        type="solver",
                        backstory="x",
                    )
                )
            session.add(Ticket(title="T", tags=["x"], status="open"))
            await session.commit()

        guardrail = HiringGuardrail()
        with patch("opencompany.company.personas.async_session", factory):
            result = await guardrail.check_hire("hire_persona", {"name": "New"})

        assert result is not None
        assert "GUARDRAIL" in result
        assert "Do NOT hire" in result

    async def test_ignores_non_hire_tools(self):
        """Non-hire tool calls are not intercepted."""
        guardrail = HiringGuardrail()
        result = await guardrail.check_hire("write_file", {})
        assert result is None


# ---------------------------------------------------------------------------
# S6: Agent SOPs
# ---------------------------------------------------------------------------
class TestSOPs:
    def test_sop_files_exist(self):
        from pathlib import Path

        sops = Path("sops")
        assert (sops / "code_review.md").exists()
        assert (sops / "project_kickoff.md").exists()
        assert (sops / "new_hire.md").exists()

    def test_load_sop_for_review_tag(self):
        content = load_sop_for_tags(["review"])
        assert "STANDARD OPERATING PROCEDURE" in content
        assert "Code Review" in content

    def test_load_sop_for_hr_tag(self):
        content = load_sop_for_tags(["hr"])
        assert "New Hire" in content

    def test_load_sop_for_unknown_tag(self):
        content = load_sop_for_tags(["blockchain"])
        assert content == ""

    def test_load_sop_deduplicates(self):
        """Multiple tags mapping to same SOP only include it once."""
        content = load_sop_for_tags(["hr", "hiring"])
        assert content.count("New Hire SOP") == 1

    def test_load_sop_multiple_tags(self):
        """Multiple distinct SOPs can be loaded."""
        content = load_sop_for_tags(["review", "hr"])
        assert "Code Review" in content
        assert "New Hire" in content
