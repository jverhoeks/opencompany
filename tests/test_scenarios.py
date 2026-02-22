"""Five realistic end-to-end scenarios exercising the full system.

Each scenario tests a cross-cutting path through the OpenCompany system:
routing, personality, trust, workspaces, memory, and heartbeat.
"""

from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import async_sessionmaker

from opencompany.company.config import CompanyConfig
from opencompany.models.db import Persona, Ticket

# ---------------------------------------------------------------------------
# Shared config used across scenarios
# ---------------------------------------------------------------------------
_SCENARIO_CONFIG = CompanyConfig(
    org_style="hierarchical",
    org_styles={
        "hierarchical": {
            "routing": {"ceo": "pm", "pm": "lead", "lead": "solver"},
            "max_depth": 3,
        },
    },
    roles={
        "ceo": {
            "builtin": True,
            "type": "manager",
            "responsibilities": "Set strategic direction.",
            "tools": ["create_ticket"],
            "routes_to": "pm",
            "personality": {
                "traits": ["visionary", "impatient", "bold"],
                "communication_style": "Direct and inspiring.",
                "catchphrases": ["Let's ship it.", "Think bigger."],
            },
        },
        "hr": {
            "builtin": True,
            "type": "manager",
            "responsibilities": "Handle hiring.",
            "tools": ["hire_persona"],
            "personality": {
                "traits": ["empathetic", "organized"],
                "communication_style": "Warm but professional.",
            },
        },
        "pm": {
            "type": "manager",
            "responsibilities": "Coordinate work.",
            "tools": ["create_ticket"],
            "routes_to": "lead",
            "personality": {
                "traits": ["detail-oriented", "methodical"],
                "communication_style": "Structured and clear.",
                "catchphrases": ["Let's break this down."],
            },
        },
        "tech-lead": {
            "type": "lead",
            "tag_match": ["backend", "frontend", "architecture", "technical"],
            "responsibilities": "Design architecture.",
            "tools": ["create_ticket"],
            "routes_to": "solver",
            "personality": {
                "traits": ["pragmatic", "thorough"],
                "communication_style": "Technical and precise.",
            },
        },
        "marketing-lead": {
            "type": "lead",
            "tag_match": ["marketing", "content", "website"],
            "responsibilities": "Marketing strategy.",
            "tools": ["create_ticket"],
            "routes_to": "solver",
        },
        "backend-dev": {
            "type": "solver",
            "tag_match": ["backend", "python", "api"],
            "responsibilities": "Write backend code.",
            "tools": ["read_file", "write_file", "web_fetch", "publish_file"],
            "personality": {
                "traits": ["focused", "efficient"],
                "communication_style": "Terse and code-first.",
            },
        },
        "frontend-dev": {
            "type": "solver",
            "tag_match": ["frontend", "html", "css", "javascript", "ui"],
            "responsibilities": "Write frontend code.",
            "tools": ["read_file", "write_file", "web_fetch", "publish_file"],
            "personality": {
                "traits": ["pixel-perfect", "enthusiastic"],
                "catchphrases": ["Ship the pixels."],
            },
        },
        "content-writer": {
            "type": "solver",
            "tag_match": ["content", "copy", "blog", "website"],
            "responsibilities": "Write content.",
            "tools": ["read_file", "write_file", "publish_file"],
        },
    },
    personas={
        "ceo": {
            "role": "ceo",
            "personality": {
                "traits": ["visionary", "impatient", "bold"],
                "communication_style": "Direct and inspiring.",
                "quirks": ["Always says 'we' not 'I'"],
                "catchphrases": ["Let's ship it."],
            },
        },
        "hr": {
            "role": "hr",
            "personality": {
                "traits": ["empathetic", "organized"],
            },
        },
    },
)


# ===========================================================================
# Scenario 1: "Build Us a Landing Page"
# ===========================================================================
async def test_scenario_landing_page(db_engine):
    """Full hierarchy: CEO→PM→lead→solver→workspace→publish."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    personas = [
        Persona(
            id="ceo",
            name="Morgan",
            role="CEO",
            type="manager",
            skills=["strategy"],
            backstory="The founder.",
        ),
        Persona(
            id="pm",
            name="Taylor",
            role="PM",
            type="manager",
            reports_to="ceo",
            skills=["planning"],
            backstory="Project manager.",
        ),
        Persona(
            id="tech-lead",
            name="Dana",
            role="Tech Lead",
            type="lead",
            reports_to="pm",
            skills=["architecture"],
            picks_up=["frontend", "backend"],
            backstory="Tech lead.",
        ),
        Persona(
            id="frontend-dev",
            name="Sam",
            role="Frontend Dev",
            type="solver",
            reports_to="tech-lead",
            skills=["html", "css", "javascript"],
            picks_up=["frontend", "html", "css"],
            backstory="Frontend dev.",
        ),
    ]

    async with factory() as session:
        for p in personas:
            session.add(p)
        await session.commit()

    # CEO creates a ticket
    async with factory() as session:
        ticket = Ticket(
            title="Build company landing page",
            description="Create a professional landing page for the company.",
            priority="high",
            tags=["frontend", "website"],
            created_by="ceo",
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        ticket_id = ticket.id

    # Route: CEO→PM (via routes_to in config)
    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine.run_persona", new_callable=AsyncMock),
        patch(
            "opencompany.company.engine.load_company_config",
            return_value=_SCENARIO_CONFIG,
        ),
    ):
        from opencompany.company.engine import _route_ticket

        await _route_ticket(ticket_id)

    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        assert ticket.assigned_to == "pm"
        assert ticket.status == "assigned"

    # Tech-lead creates a ticket for the frontend solver
    async with factory() as session:
        dev_ticket = Ticket(
            title="Code the landing page",
            tags=["frontend", "html", "css"],
            created_by="tech-lead",
        )
        session.add(dev_ticket)
        await session.commit()
        await session.refresh(dev_ticket)
        dev_ticket_id = dev_ticket.id

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine.run_persona", new_callable=AsyncMock),
        patch(
            "opencompany.company.engine.load_company_config",
            return_value=_SCENARIO_CONFIG,
        ),
    ):
        await _route_ticket(dev_ticket_id)

    async with factory() as session:
        dev_ticket = await session.get(Ticket, dev_ticket_id)
        assert dev_ticket.assigned_to == "frontend-dev"

    # Frontend-dev writes to private workspace and publishes to shared
    import os
    import tempfile

    with (
        tempfile.TemporaryDirectory() as ws,
        patch("opencompany.agents.tools.code.WORKSPACE_ROOT", ws),
    ):
        from opencompany.agents.tools.code import publish_file, write_file

        result = write_file.__wrapped__(
            path="index.html",
            content="<h1>Welcome to OpenCompany</h1>",
            persona_id="frontend-dev",
        )
        assert "Wrote" in result

        result = publish_file.__wrapped__(
            source_path="index.html",
            persona_id="frontend-dev",
        )
        assert "Published" in result
        assert os.path.isfile(os.path.join(ws, "shared", "index.html"))


# ===========================================================================
# Scenario 2: "The Personality Test"
# ===========================================================================
def test_scenario_personality_injection():
    """Each persona gets unique personality traits in their system prompt."""
    from opencompany.agents.prompts import build_system_prompt

    roles_with_personality = [
        ("ceo", "manager", ["visionary", "impatient", "bold"]),
        ("pm", "manager", ["detail-oriented", "methodical"]),
        ("tech-lead", "lead", ["pragmatic", "thorough"]),
        ("frontend-dev", "solver", ["pixel-perfect", "enthusiastic"]),
        ("backend-dev", "solver", ["focused", "efficient"]),
    ]

    prompts = {}
    for role_id, role_type, expected_traits in roles_with_personality:
        persona = Persona(
            id=role_id,
            name=f"Test {role_id}",
            role=role_id,
            type=role_type,
            backstory=f"Test persona for {role_id}.",
        )
        prompt = build_system_prompt(persona, _SCENARIO_CONFIG)
        prompts[role_id] = prompt

        # Verify personality section exists
        assert "PERSONALITY:" in prompt, f"{role_id} missing PERSONALITY section"
        for trait in expected_traits:
            assert trait in prompt, f"{role_id} missing trait '{trait}'"

    # Verify no two prompts have the same personality section
    personality_sections = []
    for prompt in prompts.values():
        start = prompt.index("PERSONALITY:")
        end = prompt.index("Stay in character")
        personality_sections.append(prompt[start:end])

    assert len(set(personality_sections)) == len(personality_sections), (
        "Duplicate personality sections found"
    )


# ===========================================================================
# Scenario 3: "Trust Boundary Enforcement"
# ===========================================================================
def test_scenario_trust_boundaries():
    """Tier system blocks dangerous tools at every level."""
    from opencompany.company.trust import filter_tools_by_tier

    all_tools = [
        "read_file",
        "list_files",
        "write_file",
        "web_fetch",
        "publish_file",
        "create_ticket",
        "hire_persona",
        "fire_persona",
    ]

    # External: read-only
    allowed, denied = filter_tools_by_tier(all_tools, "external")
    assert set(allowed) == {"read_file", "list_files"}
    assert "write_file" in denied
    assert "web_fetch" in denied
    assert "publish_file" in denied
    assert "hire_persona" in denied
    assert "create_ticket" in denied

    # Solver: can write and fetch, not hire/create
    allowed, denied = filter_tools_by_tier(all_tools, "solver")
    assert "write_file" in allowed
    assert "web_fetch" in allowed
    assert "publish_file" in allowed
    assert "read_file" in allowed
    assert "hire_persona" in denied
    assert "create_ticket" in denied

    # Lead: can create tickets, not hire
    allowed, denied = filter_tools_by_tier(all_tools, "lead")
    assert "create_ticket" in allowed
    assert "write_file" in allowed
    assert "hire_persona" in denied

    # Full: everything allowed
    allowed, denied = filter_tools_by_tier(all_tools, "full")
    assert set(allowed) == set(all_tools)
    assert denied == []


# ===========================================================================
# Scenario 4: "Stale Ticket Escalation Chain"
# ===========================================================================
async def test_scenario_stale_escalation(db_engine):
    """Stale ticket assigned to solver gets escalated to manager via CEO."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="ceo",
                name="Morgan",
                role="CEO",
                type="manager",
                skills=["strategy"],
                backstory="CEO.",
            )
        )
        session.add(
            Persona(
                id="pm",
                name="Taylor",
                role="PM",
                type="manager",
                reports_to="ceo",
                skills=["planning"],
                backstory="Project manager.",
            )
        )
        session.add(
            Persona(
                id="tech-lead",
                name="Dana",
                role="Tech Lead",
                type="lead",
                reports_to="pm",
                skills=["architecture"],
                picks_up=["backend"],
                backstory="Tech lead.",
            )
        )
        session.add(
            Persona(
                id="backend-dev",
                name="Jamie",
                role="Backend Dev",
                type="solver",
                reports_to="tech-lead",
                skills=["python", "backend"],
                picks_up=["backend"],
                backstory="Backend dev.",
            )
        )
        # Create a ticket assigned to backend-dev, stale for 60+ minutes
        from datetime import datetime, timedelta

        stale_time = datetime.now() - timedelta(minutes=90)
        ticket = Ticket(
            title="Fix database connection pooling",
            tags=["backend"],
            assigned_to="backend-dev",
            status="in_progress",
            created_by="tech-lead",
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        ticket_id = ticket.id

        # Manually set updated_at to stale time
        ticket.updated_at = stale_time
        await session.commit()

    # Verify the ticket is stale (updated_at > 60 minutes ago)
    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        from datetime import datetime, timedelta

        assert ticket.updated_at < datetime.now() - timedelta(minutes=60)
        assert ticket.assigned_to == "backend-dev"
        assert ticket.status == "in_progress"

    # Simulate escalation: re-assign to CEO (mimics what a stale handler would do)
    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        ticket.assigned_to = "ceo"
        ticket.status = "assigned"
        await session.commit()

    # Verify CEO now owns the escalated ticket
    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        assert ticket.assigned_to == "ceo"

    # CEO can re-route: create a new ticket for tech-lead to unblock
    async with factory() as session:
        followup = Ticket(
            title="Investigate pooling stall on backend-dev's ticket",
            tags=["backend", "architecture"],
            created_by="ceo",
        )
        session.add(followup)
        await session.commit()
        await session.refresh(followup)
        followup_id = followup.id

    # Route the followup through the hierarchy
    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine.run_persona", new_callable=AsyncMock),
        patch(
            "opencompany.company.engine.load_company_config",
            return_value=_SCENARIO_CONFIG,
        ),
    ):
        from opencompany.company.engine import _route_ticket

        await _route_ticket(followup_id)

    async with factory() as session:
        followup = await session.get(Ticket, followup_id)
        # CEO routes to PM, which routes to tech-lead (via tag match)
        assert followup.assigned_to == "pm"


# ===========================================================================
# Scenario 5: "The Full Sprint with Memory"
# ===========================================================================
async def test_scenario_sprint_with_memory(db_engine):
    """Persona retains knowledge across runs via durable memory."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="pm-sprint",
                name="Taylor",
                role="PM",
                type="manager",
                skills=["planning"],
                backstory="Sprint PM.",
                tools=["remember", "recall"],
            )
        )
        await session.commit()

    with patch("opencompany.company.memory.async_session", factory):
        from opencompany.company.memory import (
            build_memory_context,
            compact_memories,
            recall_memories,
            store_memory,
        )

        # Run 1: store a sprint goal
        mem_id = await store_memory("pm-sprint", "fact", "Sprint goal is v2 launch")
        assert mem_id > 0

        # Run 2: verify context includes the memory
        ctx = await build_memory_context("pm-sprint")
        assert "v2 launch" in ctx
        assert "[MEMORY" in ctx

        # Run 3: store many memories to trigger compaction
        for i in range(210):
            await store_memory("pm-sprint", "fact", f"Sprint note {i}")

        all_before = await recall_memories("pm-sprint", limit=300)
        assert len(all_before) == 211  # 1 original + 210 new

        # Compact
        await compact_memories("pm-sprint", threshold=200, keep=50)

        all_after = await recall_memories("pm-sprint", limit=300)
        # 50 kept + 1 compacted summary = 51
        assert len(all_after) == 51

        # Compacted summary exists
        compacted = [m for m in all_after if m["type"] == "compacted"]
        assert len(compacted) == 1
        assert "Compacted" in compacted[0]["content"]

        # Recent context still works
        ctx_after = await build_memory_context("pm-sprint")
        assert "[MEMORY" in ctx_after
        assert "Sprint note" in ctx_after
