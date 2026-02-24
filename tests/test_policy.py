"""Tests for policy documents system."""

from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from opencompany.models.db import Persona


# ---------------------------------------------------------------------------
# Helper: seed personas needed for policy tests
# ---------------------------------------------------------------------------
async def _seed_personas(factory):
    async with factory() as session:
        session.add_all(
            [
                Persona(
                    id="ceo-pol",
                    name="CEO",
                    role="ceo",
                    type="manager",
                    backstory="The CEO.",
                    skills=["strategy"],
                ),
                Persona(
                    id="tech-lead-pol",
                    name="Tech Lead",
                    role="tech-lead",
                    type="lead",
                    backstory="A tech lead.",
                    skills=["backend", "api"],
                ),
                Persona(
                    id="dev-pol",
                    name="Dev",
                    role="backend-dev",
                    type="solver",
                    backstory="A backend dev.",
                    skills=["python", "api"],
                ),
                Persona(
                    id="frontend-pol",
                    name="Frontend",
                    role="frontend-dev",
                    type="solver",
                    backstory="A frontend dev.",
                    skills=["javascript", "css"],
                ),
            ]
        )
        await session.commit()


# ---------------------------------------------------------------------------
# Core policy functions
# ---------------------------------------------------------------------------
async def test_create_policy(db_engine):
    """Creating a policy returns an ID and defaults to draft."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    await _seed_personas(factory)

    with patch("opencompany.company.policy.async_session", factory):
        from opencompany.company.policy import create_policy, get_policy

        pid = await create_policy(
            author_id="ceo-pol",
            title="API Design Guidelines",
            content="# API Guidelines\nUse REST.",
            tags=["engineering", "api"],
            applies_to=["backend-dev", "tech-lead"],
        )
        assert pid > 0

        policy = await get_policy(pid)
        assert policy["title"] == "API Design Guidelines"
        assert policy["status"] == "draft"
        assert policy["author_id"] == "ceo-pol"
        assert "api" in policy["tags"]
        assert "backend-dev" in policy["applies_to"]


async def test_approve_policy(db_engine):
    """Managers and leads can approve draft policies."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    await _seed_personas(factory)

    with patch("opencompany.company.policy.async_session", factory):
        from opencompany.company.policy import approve_policy, create_policy

        pid = await create_policy("ceo-pol", "Code Style", "Use ruff.", ["engineering"], ["*"])
        result = await approve_policy(pid, "tech-lead-pol")

        assert result["status"] == "approved"
        assert result["approved_by"] == "tech-lead-pol"


async def test_approve_policy_requires_manager_or_lead(db_engine):
    """Solvers cannot approve policies."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    await _seed_personas(factory)

    with patch("opencompany.company.policy.async_session", factory):
        from opencompany.company.policy import approve_policy, create_policy

        pid = await create_policy("ceo-pol", "Some Policy", "Content.", [], ["*"])
        with pytest.raises(PermissionError, match="(?i)managers and leads"):
            await approve_policy(pid, "dev-pol")


async def test_approve_non_draft_fails(db_engine):
    """Cannot approve a policy that is already approved."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    await _seed_personas(factory)

    with patch("opencompany.company.policy.async_session", factory):
        from opencompany.company.policy import approve_policy, create_policy

        pid = await create_policy("ceo-pol", "Policy", "Content.", [], ["*"])
        await approve_policy(pid, "ceo-pol")

        with pytest.raises(ValueError, match="(?i)not draft"):
            await approve_policy(pid, "ceo-pol")


async def test_reject_policy(db_engine):
    """Managers and leads can reject draft policies."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    await _seed_personas(factory)

    with patch("opencompany.company.policy.async_session", factory):
        from opencompany.company.policy import create_policy, reject_policy

        pid = await create_policy("ceo-pol", "Bad Policy", "No.", [], ["*"])
        result = await reject_policy(pid, "tech-lead-pol", "Not detailed enough")

        assert result["status"] == "rejected"
        assert result["approved_by"] == "tech-lead-pol"


async def test_reject_policy_requires_manager_or_lead(db_engine):
    """Solvers cannot reject policies."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    await _seed_personas(factory)

    with patch("opencompany.company.policy.async_session", factory):
        from opencompany.company.policy import create_policy, reject_policy

        pid = await create_policy("ceo-pol", "Policy", "Content.", [], ["*"])
        with pytest.raises(PermissionError):
            await reject_policy(pid, "dev-pol")


async def test_list_policies(db_engine):
    """List policies with optional status and tag filters."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    await _seed_personas(factory)

    with patch("opencompany.company.policy.async_session", factory):
        from opencompany.company.policy import approve_policy, create_policy, list_policies

        await create_policy("ceo-pol", "Policy A", "A", ["api"], ["*"])
        pid_b = await create_policy("ceo-pol", "Policy B", "B", ["frontend"], ["*"])
        await approve_policy(pid_b, "ceo-pol")

        # All policies
        all_p = await list_policies()
        assert len(all_p) == 2

        # Filter by status
        approved = await list_policies(status="approved")
        assert len(approved) == 1
        assert approved[0]["title"] == "Policy B"

        drafts = await list_policies(status="draft")
        assert len(drafts) == 1
        assert drafts[0]["title"] == "Policy A"

        # Filter by tag
        api_p = await list_policies(tag="api")
        assert len(api_p) == 1
        assert api_p[0]["title"] == "Policy A"


async def test_get_policy_not_found(db_engine):
    """get_policy returns None for nonexistent ID."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    with patch("opencompany.company.policy.async_session", factory):
        from opencompany.company.policy import get_policy

        result = await get_policy(9999)
        assert result is None


# ---------------------------------------------------------------------------
# build_policy_context — prompt injection
# ---------------------------------------------------------------------------
async def test_build_policy_context_wildcard(db_engine):
    """Policies with applies_to=["*"] match all personas."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    await _seed_personas(factory)

    with patch("opencompany.company.policy.async_session", factory):
        from opencompany.company.policy import (
            approve_policy,
            build_policy_context,
            create_policy,
        )

        pid = await create_policy("ceo-pol", "Global Policy", "Follow this.", ["general"], ["*"])
        await approve_policy(pid, "ceo-pol")

        # Should match dev-pol (any persona)
        dev = Persona(
            id="dev-pol",
            name="Dev",
            role="backend-dev",
            type="solver",
            backstory="",
            skills=["python"],
        )
        ctx = await build_policy_context(dev)
        assert "[COMPANY POLICIES]" in ctx
        assert "Global Policy" in ctx
        assert "[END POLICIES]" in ctx


async def test_build_policy_context_role_match(db_engine):
    """Policies matching a persona's role are included."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    await _seed_personas(factory)

    with patch("opencompany.company.policy.async_session", factory):
        from opencompany.company.policy import (
            approve_policy,
            build_policy_context,
            create_policy,
        )

        pid = await create_policy(
            "ceo-pol",
            "Backend Standards",
            "Use async.",
            ["engineering"],
            ["backend-dev"],
        )
        await approve_policy(pid, "ceo-pol")

        # backend-dev role matches
        dev = Persona(
            id="dev-pol",
            name="Dev",
            role="backend-dev",
            type="solver",
            backstory="",
            skills=[],
        )
        ctx = await build_policy_context(dev)
        assert "Backend Standards" in ctx

        # frontend-dev role does NOT match
        fe = Persona(
            id="frontend-pol",
            name="FE",
            role="frontend-dev",
            type="solver",
            backstory="",
            skills=[],
        )
        ctx_fe = await build_policy_context(fe)
        assert ctx_fe == ""


async def test_build_policy_context_persona_id_match(db_engine):
    """Policies targeting a specific persona ID are included."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    await _seed_personas(factory)

    with patch("opencompany.company.policy.async_session", factory):
        from opencompany.company.policy import (
            approve_policy,
            build_policy_context,
            create_policy,
        )

        pid = await create_policy(
            "ceo-pol",
            "Dev-Specific",
            "Special rules.",
            [],
            ["dev-pol"],
        )
        await approve_policy(pid, "ceo-pol")

        dev = Persona(
            id="dev-pol",
            name="Dev",
            role="backend-dev",
            type="solver",
            backstory="",
            skills=[],
        )
        ctx = await build_policy_context(dev)
        assert "Dev-Specific" in ctx


async def test_build_policy_context_tag_skill_match(db_engine):
    """Policies whose tags overlap with persona skills are included."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    await _seed_personas(factory)

    with patch("opencompany.company.policy.async_session", factory):
        from opencompany.company.policy import (
            approve_policy,
            build_policy_context,
            create_policy,
        )

        pid = await create_policy(
            "ceo-pol",
            "API Policy",
            "RESTful only.",
            ["api"],
            [],
        )
        await approve_policy(pid, "ceo-pol")

        # dev with "api" skill matches
        dev = Persona(
            id="dev-pol",
            name="Dev",
            role="backend-dev",
            type="solver",
            backstory="",
            skills=["python", "api"],
        )
        ctx = await build_policy_context(dev)
        assert "API Policy" in ctx

        # dev without "api" skill does NOT match
        fe = Persona(
            id="frontend-pol",
            name="FE",
            role="frontend-dev",
            type="solver",
            backstory="",
            skills=["javascript", "css"],
        )
        ctx_fe = await build_policy_context(fe)
        assert ctx_fe == ""


async def test_build_policy_context_draft_excluded(db_engine):
    """Draft policies are NOT injected into prompts."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    await _seed_personas(factory)

    with patch("opencompany.company.policy.async_session", factory):
        from opencompany.company.policy import build_policy_context, create_policy

        await create_policy("ceo-pol", "Draft Policy", "Not yet.", [], ["*"])

        dev = Persona(
            id="dev-pol",
            name="Dev",
            role="backend-dev",
            type="solver",
            backstory="",
            skills=[],
        )
        ctx = await build_policy_context(dev)
        assert ctx == ""


async def test_build_policy_context_empty(db_engine):
    """Returns empty string when no approved policies exist."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    with patch("opencompany.company.policy.async_session", factory):
        from opencompany.company.policy import build_policy_context

        dev = Persona(
            id="dev-pol",
            name="Dev",
            role="backend-dev",
            type="solver",
            backstory="",
            skills=[],
        )
        ctx = await build_policy_context(dev)
        assert ctx == ""


# ---------------------------------------------------------------------------
# Tool wrappers
# ---------------------------------------------------------------------------
def test_write_policy_tool():
    """write_policy tool calls create_policy via _run_async."""
    from opencompany.agents.tools.policy import write_policy

    with patch("opencompany.utils._run_async", return_value=7):
        result = write_policy.__wrapped__(
            title="Test Policy",
            content="Content here",
            tags=["eng"],
            applies_to=["*"],
            persona_id="ceo-1",
        )

    assert "#7" in result
    assert "Test Policy" in result
    assert "draft" in result.lower()


def test_approve_policy_tool():
    """approve_policy tool calls approve_policy via _run_async."""
    from opencompany.agents.tools.policy import approve_policy

    mock_result = {"id": 3, "title": "My Policy", "status": "approved"}
    with patch("opencompany.utils._run_async", return_value=mock_result):
        result = approve_policy.__wrapped__(policy_id=3, persona_id="ceo-1")

    assert "#3" in result
    assert "approved" in result.lower()


def test_approve_policy_tool_error():
    """approve_policy tool handles PermissionError gracefully."""
    from opencompany.agents.tools.policy import approve_policy

    with patch(
        "opencompany.utils._run_async",
        side_effect=PermissionError("Only managers"),
    ):
        result = approve_policy.__wrapped__(policy_id=3, persona_id="dev-1")

    assert "cannot approve" in result.lower()


def test_list_policies_tool():
    """list_policies tool formats policy list."""
    from opencompany.agents.tools.policy import list_policies

    mock_policies = [
        {
            "id": 1,
            "status": "approved",
            "title": "Policy A",
            "author_id": "ceo",
            "tags": ["eng"],
            "applies_to": ["*"],
        },
        {
            "id": 2,
            "status": "draft",
            "title": "Policy B",
            "author_id": "pm",
            "tags": [],
            "applies_to": ["backend-dev"],
        },
    ]
    with patch("opencompany.utils._run_async", return_value=mock_policies):
        result = list_policies.__wrapped__(persona_id="dev-1")

    assert "#1" in result
    assert "Policy A" in result
    assert "#2" in result
    assert "Policy B" in result


def test_list_policies_tool_empty():
    """list_policies tool returns message when no policies found."""
    from opencompany.agents.tools.policy import list_policies

    with patch("opencompany.utils._run_async", return_value=[]):
        result = list_policies.__wrapped__(persona_id="dev-1")

    assert "no policies" in result.lower()


def test_read_policy_tool():
    """read_policy tool formats full policy."""
    from opencompany.agents.tools.policy import read_policy

    mock_policy = {
        "id": 1,
        "title": "API Guide",
        "content": "# Guidelines\nBe RESTful.",
        "status": "approved",
        "author_id": "ceo",
        "approved_by": "tech-lead",
        "tags": ["api"],
        "applies_to": ["*"],
        "version": 1,
        "created_at": "2026-02-23T00:00:00",
        "updated_at": "2026-02-23T00:00:00",
    }
    with patch("opencompany.utils._run_async", return_value=mock_policy):
        result = read_policy.__wrapped__(policy_id=1, persona_id="dev-1")

    assert "API Guide" in result
    assert "Be RESTful" in result
    assert "approved" in result.lower()


def test_read_policy_tool_not_found():
    """read_policy tool returns message when policy not found."""
    from opencompany.agents.tools.policy import read_policy

    with patch("opencompany.utils._run_async", return_value=None):
        result = read_policy.__wrapped__(policy_id=999, persona_id="dev-1")

    assert "not found" in result.lower()
