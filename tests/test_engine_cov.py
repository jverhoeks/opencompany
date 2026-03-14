"""Extended engine.py tests: events, state, greedy pickup, HR pickup."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import async_sessionmaker

from opencompany.company.config import CompanyConfig
from opencompany.models.db import Persona, Ticket

_TEST_CONFIG = CompanyConfig(
    org_style="hierarchical",
    org_styles={
        "hierarchical": {
            "routing": {"ceo": "pm", "pm": "lead", "lead": "solver"},
            "max_depth": 3,
        },
    },
    roles={
        "ceo": {"builtin": True, "type": "manager", "tools": ["create_ticket"]},
        "hr": {"builtin": True, "type": "manager", "tools": ["hire_persona"]},
        "pm": {"type": "manager", "tools": ["create_ticket"], "routes_to": "lead"},
        "tech-lead": {
            "type": "lead",
            "tag_match": ["backend", "frontend", "api"],
            "tools": ["create_ticket"],
            "routes_to": "solver",
        },
    },
    personas={},
)


# ---------------------------------------------------------------------------
# handle_event dispatching
# ---------------------------------------------------------------------------
async def test_handle_event_dispatches_ticket_created(db_engine):
    """handle_event routes ticket.created events to _route_ticket."""
    with patch("opencompany.company.engine._route_ticket", new_callable=AsyncMock) as mock_route:
        from opencompany.company.engine import handle_event

        await handle_event("ticket.created", {"ticket_id": 42})
        mock_route.assert_awaited_once_with(42)


async def test_handle_event_dispatches_ticket_review(db_engine):
    """handle_event routes ticket.review events to _trigger_review."""
    with patch(
        "opencompany.company.engine._trigger_review", new_callable=AsyncMock
    ) as mock_review:
        from opencompany.company.engine import handle_event

        await handle_event("ticket.review", {"ticket_id": 7})
        mock_review.assert_awaited_once_with(7)


async def test_handle_event_ignores_unknown_type():
    """Unknown event types are silently ignored."""
    from opencompany.company.engine import handle_event

    # Should not raise
    await handle_event("unknown.event", {"foo": "bar"})


async def test_handle_event_catches_errors():
    """Errors in handlers are caught and logged, not raised."""
    with patch(
        "opencompany.company.engine._route_ticket",
        new_callable=AsyncMock,
        side_effect=RuntimeError("DB error"),
    ):
        from opencompany.company.engine import handle_event

        # Should not raise
        await handle_event("ticket.created", {"ticket_id": 1})


# ---------------------------------------------------------------------------
# set_persona_state
# ---------------------------------------------------------------------------
async def test_set_persona_state(db_engine):
    """set_persona_state updates activity_state in the DB."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="state-dev",
                name="State Dev",
                role="Dev",
                type="solver",
                skills=["python"],
                backstory="Test.",
                activity_state="idle",
            )
        )
        await session.commit()

    with patch("opencompany.company.engine.async_session", factory):
        from opencompany.company.engine import set_persona_state

        await set_persona_state("state-dev", "working")

    async with factory() as session:
        persona = await session.get(Persona, "state-dev")
        assert persona.activity_state == "working"


async def test_set_persona_state_missing_persona(db_engine):
    """set_persona_state does nothing when persona doesn't exist."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    with patch("opencompany.company.engine.async_session", factory):
        from opencompany.company.engine import set_persona_state

        # Should not raise
        await set_persona_state("nonexistent", "working")


# ---------------------------------------------------------------------------
# _set_ticket_in_progress
# ---------------------------------------------------------------------------
async def test_set_ticket_in_progress(db_engine):
    """_set_ticket_in_progress marks an assigned ticket as in_progress."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="solver-1",
                name="Solver",
                role="Dev",
                type="solver",
                skills=["python"],
                backstory="Dev.",
            )
        )
        ticket = Ticket(
            title="Test ticket",
            priority="medium",
            status="assigned",
            tags=["backend"],
            assigned_to="solver-1",
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        ticket_id = ticket.id

    with patch("opencompany.company.engine.async_session", factory):
        from opencompany.company.engine import _set_ticket_in_progress

        await _set_ticket_in_progress(ticket_id, "solver-1")

    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        assert ticket.status == "in_progress"


async def test_set_ticket_in_progress_skips_done_ticket(db_engine):
    """_set_ticket_in_progress does not change tickets already done."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        ticket = Ticket(
            title="Done ticket",
            priority="low",
            status="done",
            tags=[],
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        ticket_id = ticket.id

    with patch("opencompany.company.engine.async_session", factory):
        from opencompany.company.engine import _set_ticket_in_progress

        await _set_ticket_in_progress(ticket_id, "anyone")

    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        assert ticket.status == "done"


# ---------------------------------------------------------------------------
# _add_ticket_tokens
# ---------------------------------------------------------------------------
async def test_add_ticket_tokens(db_engine):
    """_add_ticket_tokens accumulates token counts."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        ticket = Ticket(
            title="Token ticket",
            priority="medium",
            status="open",
            tags=[],
            tokens_in=100,
            tokens_out=50,
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        ticket_id = ticket.id

    with patch("opencompany.company.engine.async_session", factory):
        from opencompany.company.engine import _add_ticket_tokens

        await _add_ticket_tokens(ticket_id, 200, 100)

    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        assert ticket.tokens_in == 300
        assert ticket.tokens_out == 150


async def test_add_ticket_tokens_missing_ticket(db_engine):
    """_add_ticket_tokens does nothing when ticket doesn't exist."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    with patch("opencompany.company.engine.async_session", factory):
        from opencompany.company.engine import _add_ticket_tokens

        # Should not raise
        await _add_ticket_tokens(99999, 100, 50)


# ---------------------------------------------------------------------------
# _trigger_review
# ---------------------------------------------------------------------------
async def test_trigger_review_falls_back_to_manager(db_engine):
    """When creator not found, review falls back to an active manager."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="mgr",
                name="Manager",
                role="PM",
                type="manager",
                skills=["management"],
                backstory="A manager.",
            )
        )
        ticket = Ticket(
            title="Review me",
            priority="high",
            status="review",
            tags=["backend"],
            result="Done.",
            created_by="ghost",  # non-existent creator
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        ticket_id = ticket.id

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine.run_persona", new_callable=AsyncMock),
    ):
        from opencompany.company.engine import _trigger_review

        await _trigger_review(ticket_id)

    # The manager should have been selected as reviewer (spawns bg task)


async def test_trigger_review_ticket_not_found(db_engine):
    """_trigger_review handles missing ticket gracefully."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    with patch("opencompany.company.engine.async_session", factory):
        from opencompany.company.engine import _trigger_review

        # Should not raise
        await _trigger_review(99999)


# ---------------------------------------------------------------------------
# _spawn_persona_task — full lifecycle
# ---------------------------------------------------------------------------
async def test_spawn_persona_task_full_run(db_engine):
    """_spawn_persona_task runs persona, consumes tokens, sets idle state."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="spawn-dev",
                name="Spawn Dev",
                role="Dev",
                type="solver",
                skills=["python"],
                backstory="Spawner.",
                activity_state="idle",
                daily_token_budget=100000,
            )
        )
        ticket = Ticket(
            title="Spawn task",
            priority="medium",
            status="assigned",
            tags=["backend"],
            assigned_to="spawn-dev",
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        ticket_id = ticket.id

    mock_result = MagicMock()
    mock_result.input_tokens = 500
    mock_result.output_tokens = 200

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch(
            "opencompany.company.engine.run_persona",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
        patch("opencompany.company.budget.async_session", factory),
    ):
        from opencompany.company.engine import _spawn_persona_task

        async with factory() as session:
            persona = await session.get(Persona, "spawn-dev")

        _spawn_persona_task(persona, "Do work", "test-spawn", ticket_id=ticket_id)
        await asyncio.sleep(0.5)

    async with factory() as session:
        persona = await session.get(Persona, "spawn-dev")
        assert persona.activity_state == "idle"
        ticket = await session.get(Ticket, ticket_id)
        assert ticket.tokens_in == 500
        assert ticket.tokens_out == 200


async def test_spawn_persona_task_error_sets_blocked(db_engine):
    """_spawn_persona_task sets persona to blocked on error."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="err-dev",
                name="Error Dev",
                role="Dev",
                type="solver",
                skills=["python"],
                backstory="Will error.",
                activity_state="idle",
                daily_token_budget=100000,
            )
        )
        await session.commit()

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch(
            "opencompany.company.engine.run_persona",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM down"),
        ),
        patch("opencompany.company.budget.async_session", factory),
    ):
        from opencompany.company.engine import _spawn_persona_task

        async with factory() as session:
            persona = await session.get(Persona, "err-dev")

        _spawn_persona_task(persona, "Do work", "test-error")
        await asyncio.sleep(0.5)

    async with factory() as session:
        persona = await session.get(Persona, "err-dev")
        assert persona.activity_state == "blocked"


# ---------------------------------------------------------------------------
# _greedy_pickup
# ---------------------------------------------------------------------------
async def test_greedy_pickup_finds_matching_ticket(db_engine):
    """Greedy pickup routes the best matching open ticket."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="greedy-dev",
                name="Greedy Dev",
                role="Dev",
                type="solver",
                skills=["python"],
                picks_up=["backend"],
                backstory="Dev.",
            )
        )
        ticket = Ticket(
            title="Open backend task",
            priority="medium",
            status="open",
            tags=["backend"],
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        ticket_id = ticket.id

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.taskboard.async_session", factory),
        patch("opencompany.company.engine.run_persona", new_callable=AsyncMock),
        patch(
            "opencompany.company.engine.load_company_config",
            return_value=_TEST_CONFIG,
        ),
    ):
        from opencompany.company.engine import _greedy_pickup

        async with factory() as session:
            persona = await session.get(Persona, "greedy-dev")

        await _greedy_pickup(persona)

    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        assert ticket.assigned_to == "greedy-dev"
        assert ticket.status == "assigned"


async def test_greedy_pickup_no_orphans(db_engine):
    """Greedy pickup does nothing when no open tickets exist."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="idle-dev",
                name="Idle Dev",
                role="Dev",
                type="solver",
                skills=["python"],
                picks_up=["backend"],
                backstory="Dev.",
            )
        )
        await session.commit()

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.taskboard.async_session", factory),
        patch("opencompany.company.engine.load_company_config", return_value=_TEST_CONFIG),
    ):
        from opencompany.company.engine import _greedy_pickup

        async with factory() as session:
            persona = await session.get(Persona, "idle-dev")

        await _greedy_pickup(persona)

    # No open tickets → claim_next returns None → no task spawned


async def test_greedy_pickup_no_config():
    """Greedy pickup exits early when no company config exists."""
    with patch(
        "opencompany.company.engine.load_company_config",
        side_effect=FileNotFoundError,
    ):
        from opencompany.company.engine import _greedy_pickup

        persona = MagicMock()
        persona.type = "solver"
        persona.picks_up = ["backend"]
        persona.skills = ["python"]

        # Should not raise
        await _greedy_pickup(persona)


# ---------------------------------------------------------------------------
# _hr_pickup
# ---------------------------------------------------------------------------
async def test_hr_pickup_finds_hr_tagged_tickets(db_engine):
    """HR pickup routes open HR-tagged tickets."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="hr",
                name="HR",
                role="HR",
                type="manager",
                skills=["hiring"],
                backstory="HR.",
            )
        )
        ticket = Ticket(
            title="Hire backend dev",
            priority="medium",
            status="open",
            tags=["hr", "hiring"],
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        ticket_id = ticket.id

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine._route_ticket", new_callable=AsyncMock) as mock_route,
    ):
        from opencompany.company.engine import _hr_pickup

        await _hr_pickup()

    mock_route.assert_awaited_once_with(ticket_id)


async def test_hr_pickup_ignores_non_hr_tickets(db_engine):
    """HR pickup skips tickets without HR-related tags."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        ticket = Ticket(
            title="Fix backend bug",
            priority="medium",
            status="open",
            tags=["backend"],
        )
        session.add(ticket)
        await session.commit()

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine._route_ticket", new_callable=AsyncMock) as mock_route,
    ):
        from opencompany.company.engine import _hr_pickup

        await _hr_pickup()

    mock_route.assert_not_awaited()


# ---------------------------------------------------------------------------
# _escalate_to_ceo
# ---------------------------------------------------------------------------
async def test_escalate_to_ceo(db_engine):
    """Unmatched ticket is assigned to CEO with escalation log."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="ceo",
                name="CEO",
                role="CEO",
                type="manager",
                skills=["strategy"],
                backstory="The boss.",
            )
        )
        ticket = Ticket(
            title="Unknown domain task",
            priority="high",
            status="open",
            tags=["blockchain"],
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        ticket_id = ticket.id

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine.run_persona", new_callable=AsyncMock),
    ):
        from opencompany.company.engine import _escalate_to_ceo

        async with factory() as session:
            ticket = await session.get(Ticket, ticket_id)
            await _escalate_to_ceo(ticket, session)

    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        assert ticket.assigned_to == "ceo"
        assert ticket.status == "assigned"


async def test_escalate_to_ceo_inactive(db_engine):
    """Escalation fails gracefully when CEO is not active."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        ticket = Ticket(
            title="No CEO available",
            priority="high",
            status="open",
            tags=["blockchain"],
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        ticket_id = ticket.id

    with patch("opencompany.company.engine.async_session", factory):
        from opencompany.company.engine import _escalate_to_ceo

        async with factory() as session:
            ticket = await session.get(Ticket, ticket_id)
            await _escalate_to_ceo(ticket, session)

    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        assert ticket.assigned_to is None  # CEO not available


# ---------------------------------------------------------------------------
# _build_task_prompt
# ---------------------------------------------------------------------------
def test_build_task_prompt():
    """_build_task_prompt includes ticket details."""
    from opencompany.company.engine import _build_task_prompt

    ticket = MagicMock()
    ticket.id = 42
    ticket.title = "Fix login"
    ticket.description = "Users can't log in"
    ticket.priority = "high"
    ticket.tags = ["backend", "auth"]
    ticket.context = "Related to PR #99"

    prompt = _build_task_prompt(ticket)
    assert "#42" in prompt
    assert "Fix login" in prompt
    assert "Users can't log in" in prompt
    assert "high" in prompt
    assert "backend" in prompt
    assert "auth" in prompt
    assert "Related to PR #99" in prompt


# ---------------------------------------------------------------------------
# _get_routing_target
# ---------------------------------------------------------------------------
def test_get_routing_target_no_creator():
    """No creator routes to solver."""
    from opencompany.company.engine import _get_routing_target

    result = _get_routing_target(None, _TEST_CONFIG, {"ceo": "pm"})
    assert result == "solver"


def test_get_routing_target_by_id():
    """Creator ID found in routing table."""
    from opencompany.company.engine import _get_routing_target

    creator = MagicMock()
    creator.id = "ceo"
    result = _get_routing_target(creator, _TEST_CONFIG, {"ceo": "pm"})
    assert result == "pm"


def test_get_routing_target_by_role_type():
    """Creator type found in routing table."""
    from opencompany.company.engine import _get_routing_target

    creator = MagicMock()
    creator.id = "some-lead"
    creator.type = "lead"
    result = _get_routing_target(creator, _TEST_CONFIG, {"lead": "solver"})
    assert result == "solver"


def test_get_routing_target_lead_default():
    """Lead type defaults to solver when not in routing table."""
    from opencompany.company.engine import _get_routing_target

    creator = MagicMock()
    creator.id = "some-lead"
    creator.type = "lead"
    result = _get_routing_target(creator, _TEST_CONFIG, {})
    assert result == "solver"


# ---------------------------------------------------------------------------
# _find_lead_for_tags
# ---------------------------------------------------------------------------
def test_find_lead_for_tags_exact_match():
    """Exact tag match returns the matching lead."""
    from opencompany.company.engine import _find_lead_for_tags

    result = _find_lead_for_tags(["backend"], _TEST_CONFIG)
    assert result == "tech-lead"


def test_find_lead_for_tags_no_match():
    """No matching tags returns None."""
    from opencompany.company.engine import _find_lead_for_tags

    result = _find_lead_for_tags(["blockchain"], _TEST_CONFIG)
    assert result is None


# ---------------------------------------------------------------------------
# sweep_unassigned_tickets — no orphans
# ---------------------------------------------------------------------------
async def test_sweep_no_orphans(db_engine):
    """Sweep returns 0 when no open unassigned tickets exist."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    with patch("opencompany.company.engine.async_session", factory):
        from opencompany.company.engine import sweep_unassigned_tickets

        count = await sweep_unassigned_tickets()
        assert count == 0


async def test_sweep_handles_route_error(db_engine):
    """Sweep continues when a single ticket route fails."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="dev",
                name="Dev",
                role="Dev",
                type="solver",
                skills=["python"],
                picks_up=["backend"],
                backstory="Dev.",
            )
        )
        session.add(Ticket(title="Task 1", priority="medium", status="open", tags=["backend"]))
        session.add(Ticket(title="Task 2", priority="medium", status="open", tags=["backend"]))
        await session.commit()

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch(
            "opencompany.company.engine._route_ticket",
            new_callable=AsyncMock,
            side_effect=[RuntimeError("DB fail"), None],
        ) as mock_route,
        patch("opencompany.company.engine.load_company_config", return_value=_TEST_CONFIG),
    ):
        from opencompany.company.engine import sweep_unassigned_tickets

        count = await sweep_unassigned_tickets()

    # Both were attempted, only second succeeded
    assert mock_route.await_count == 2
    assert count == 1


# ---------------------------------------------------------------------------
# start_event_listener
# ---------------------------------------------------------------------------
async def test_start_event_listener():
    """start_event_listener calls subscribe with handle_event."""
    with patch("opencompany.company.engine.subscribe", new_callable=AsyncMock) as mock_sub:
        from opencompany.company.engine import handle_event, start_event_listener

        await start_event_listener()
        mock_sub.assert_awaited_once_with(handle_event)


# ---------------------------------------------------------------------------
# HR-tagged tickets route to HR
# ---------------------------------------------------------------------------
async def test_hr_tagged_ticket_routes_to_hr(db_engine):
    """A ticket tagged 'hr' is always routed to the HR persona."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Persona(
                id="hr",
                name="HR",
                role="HR",
                type="manager",
                skills=["hiring"],
                backstory="HR.",
            )
        )
        ticket = Ticket(
            title="Need to hire a designer",
            priority="medium",
            status="open",
            tags=["hr"],
            created_by="ceo",
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        ticket_id = ticket.id

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine.run_persona", new_callable=AsyncMock),
        patch("opencompany.company.engine.load_company_config", return_value=_TEST_CONFIG),
    ):
        from opencompany.company.engine import _route_ticket

        await _route_ticket(ticket_id)

    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        assert ticket.assigned_to == "hr"
        assert ticket.status == "assigned"


# ---------------------------------------------------------------------------
# Route ticket skips non-open tickets
# ---------------------------------------------------------------------------
async def test_route_ticket_skips_assigned(db_engine):
    """_route_ticket skips tickets that are already assigned."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        ticket = Ticket(
            title="Already assigned",
            priority="medium",
            status="assigned",
            tags=["backend"],
            assigned_to="dev-1",
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        ticket_id = ticket.id

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch("opencompany.company.engine.load_company_config", return_value=_TEST_CONFIG),
    ):
        from opencompany.company.engine import _route_ticket

        await _route_ticket(ticket_id)

    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        # Should remain assigned, not re-routed
        assert ticket.status == "assigned"
        assert ticket.assigned_to == "dev-1"


async def test_route_ticket_no_config(db_engine):
    """_route_ticket logs warning when no config file exists."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        ticket = Ticket(
            title="No config",
            priority="medium",
            status="open",
            tags=["backend"],
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        ticket_id = ticket.id

    with (
        patch("opencompany.company.engine.async_session", factory),
        patch(
            "opencompany.company.engine.load_company_config",
            side_effect=FileNotFoundError,
        ),
    ):
        from opencompany.company.engine import _route_ticket

        await _route_ticket(ticket_id)

    async with factory() as session:
        ticket = await session.get(Ticket, ticket_id)
        # Should stay open, not routed
        assert ticket.status == "open"
