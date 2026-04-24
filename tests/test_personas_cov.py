"""Additional coverage tests for persona management edge cases."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from opencompany.company.personas import (
    _append_to_company_yaml,
    _fire_persona,
    _hire_persona,
    fire_persona_sync,
    hire_persona_sync,
    list_personas_sync,
)
from opencompany.models.db import Persona, Ticket
from tests.conftest import mock_run_async


@pytest.fixture
async def persona_session(db_engine):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    with patch("opencompany.company.personas.async_session", factory):
        yield factory


# ---------------------------------------------------------------------------
# _hire_persona edge cases
# ---------------------------------------------------------------------------
async def test_hire_invalid_persona_id(persona_session):
    """Invalid persona IDs (with spaces/special chars) are rejected."""
    result = await _hire_persona(
        persona_id="bad id!",
        name="Test",
        role="Dev",
        persona_type="solver",
        skills=[],
        backstory="x",
    )
    assert "Error" in result
    assert "invalid persona_id" in result


async def test_hire_with_all_optional_fields(persona_session, tmp_path):
    """Hiring with reports_to, tools, and picks_up sets them on the persona."""
    with (
        patch("opencompany.company.personas.os.makedirs"),
        patch("opencompany.company.personas._append_to_company_yaml"),
        patch(
            "opencompany.company.config.load_company_config",
            side_effect=Exception("no config"),
        ),
    ):
        result = await _hire_persona(
            persona_id="full-dev",
            name="Full Dev",
            role="Full Stack Dev",
            persona_type="solver",
            skills=["python", "js"],
            backstory="A full-stack engineer.",
            reports_to="ceo",
            tools=["read_file", "write_file"],
            picks_up=["backend", "frontend"],
        )

    assert "Hired Full Dev" in result

    async with persona_session() as session:
        persona = await session.get(Persona, "full-dev")
        assert persona.reports_to == "ceo"
        assert persona.tools == ["read_file", "write_file"]
        assert persona.picks_up == ["backend", "frontend"]


async def test_hire_loads_role_config(persona_session, tmp_path):
    """Hiring auto-fills picks_up, tools, model_id from role config."""
    mock_config = type(
        "Config",
        (),
        {
            "roles": {
                "developer": {
                    "tag_match": ["dev"],
                    "tools": ["read_file"],
                    "model": "gpt-4",
                    "daily_token_budget": 5000,
                }
            }
        },
    )()

    with (
        patch("opencompany.company.personas.os.makedirs"),
        patch("opencompany.company.personas._append_to_company_yaml"),
        patch(
            "opencompany.company.config.load_company_config",
            return_value=mock_config,
        ),
    ):
        result = await _hire_persona(
            persona_id="cfg-dev",
            name="Config Dev",
            role="Developer",
            persona_type="solver",
            skills=["python"],
            backstory="Uses role config.",
        )

    assert "Hired Config Dev" in result

    async with persona_session() as session:
        persona = await session.get(Persona, "cfg-dev")
        assert persona.model_id == "gpt-4"
        assert persona.daily_token_budget == 5000
        assert persona.picks_up == ["dev"]
        assert persona.tools == ["read_file"]


async def test_hire_post_sweep(persona_session):
    """Post-hire sweep is attempted and result is logged."""
    with (
        patch("opencompany.company.personas.os.makedirs"),
        patch("opencompany.company.personas._append_to_company_yaml"),
        patch(
            "opencompany.company.config.load_company_config",
            side_effect=Exception("no config"),
        ),
        patch(
            "opencompany.company.engine.sweep_unassigned_tickets",
            new_callable=AsyncMock,
            return_value=3,
        ),
    ):
        result = await _hire_persona(
            persona_id="sweep-dev",
            name="Sweep Dev",
            role="Dev",
            persona_type="solver",
            skills=[],
            backstory="x",
        )

    assert "Hired Sweep Dev" in result


async def test_hire_post_sweep_failure(persona_session):
    """Post-hire sweep failure is handled gracefully."""
    with (
        patch("opencompany.company.personas.os.makedirs"),
        patch("opencompany.company.personas._append_to_company_yaml"),
        patch(
            "opencompany.company.config.load_company_config",
            side_effect=Exception("no config"),
        ),
        patch(
            "opencompany.company.engine.sweep_unassigned_tickets",
            new_callable=AsyncMock,
            side_effect=RuntimeError("engine not ready"),
        ),
    ):
        result = await _hire_persona(
            persona_id="sweep-fail",
            name="Sweep Fail",
            role="Dev",
            persona_type="solver",
            skills=[],
            backstory="x",
        )

    assert "Hired Sweep Fail" in result


# ---------------------------------------------------------------------------
# _fire_persona edge cases
# ---------------------------------------------------------------------------
async def test_fire_persona_reassigns_orphaned_tickets(persona_session):
    """Firing a persona reassigns their in-progress tickets to open pool.

    Also republishes ``ticket.created`` for each orphan so routing fires
    immediately rather than waiting for the 30-second sweep.
    """
    async with persona_session() as session:
        session.add(
            Persona(
                id="busy-dev",
                name="Busy Dev",
                role="Dev",
                type="solver",
                backstory="Has tickets.",
            )
        )
        await session.flush()

        session.add(
            Ticket(
                title="Task A",
                assigned_to="busy-dev",
                status="in_progress",
            )
        )
        session.add(
            Ticket(
                title="Task B",
                assigned_to="busy-dev",
                status="assigned",
            )
        )
        session.add(
            Ticket(
                title="Task C",
                assigned_to="busy-dev",
                status="done",
            )
        )
        await session.commit()

    published: list[tuple[str, dict]] = []

    async def fake_publish(event_type, data):
        published.append((event_type, data))

    with patch("opencompany.events.bus.publish", fake_publish):
        result = await _fire_persona("busy-dev", reason="restructure")
    assert "Fired Busy Dev" in result

    async with persona_session() as session:
        persona = await session.get(Persona, "busy-dev")
        assert persona is not None
        assert persona.status == "fired"

        from sqlalchemy import select

        tickets = (await session.execute(select(Ticket))).scalars().all()
        open_tickets = [t for t in tickets if t.status == "open"]
        done_tickets = [t for t in tickets if t.status == "done"]
        # The 2 active tickets should be unassigned/open, done stays done
        assert len(open_tickets) == 2
        assert len(done_tickets) == 1
        for t in open_tickets:
            assert t.assigned_to is None

    # Exactly two ticket.created events — one per reclaimed orphan.
    created_events = [d for e, d in published if e == "ticket.created"]
    assert len(created_events) == 2
    assert all("ticket_id" in d for d in created_events)


# ---------------------------------------------------------------------------
# _append_to_company_yaml
# ---------------------------------------------------------------------------
def test_append_to_company_yaml(tmp_path):
    """Successfully appends a persona to company.yaml."""
    import yaml

    yaml_file = tmp_path / "company.yaml"
    yaml_file.write_text(yaml.dump({"personas": {"ceo": {"role": "ceo"}}}))

    with (
        patch("opencompany.company.personas.os.path.join", return_value=str(yaml_file)),
        patch("opencompany.company.personas.os.path.exists", return_value=True),
        patch("opencompany.company.config.invalidate_cache"),
    ):
        _append_to_company_yaml(
            persona_id="new-dev",
            name="New Dev",
            role="Developer",
            persona_type="solver",
            skills=["python"],
            backstory="A new developer.",
            reports_to="ceo",
            tools=["read_file"],
            picks_up=["dev"],
        )

    data = yaml.safe_load(yaml_file.read_text())
    assert "new-dev" in data["personas"]
    assert data["personas"]["new-dev"]["name"] == "New Dev"
    assert data["personas"]["new-dev"]["reports_to"] == "ceo"


def test_append_to_company_yaml_no_file():
    """No-op when company.yaml doesn't exist."""
    with patch("opencompany.company.personas.os.path.exists", return_value=False):
        # Should not raise
        _append_to_company_yaml("x", "X", "Dev", "solver", [], "x", None, None, None)


def test_append_to_company_yaml_already_exists(tmp_path):
    """Skips if persona_id is already in the YAML."""
    import yaml

    yaml_file = tmp_path / "company.yaml"
    yaml_file.write_text(yaml.dump({"personas": {"existing": {"role": "dev"}}}))

    with (
        patch("opencompany.company.personas.os.path.join", return_value=str(yaml_file)),
        patch("opencompany.company.personas.os.path.exists", return_value=True),
    ):
        _append_to_company_yaml(
            persona_id="existing",
            name="Existing",
            role="Dev",
            persona_type="solver",
            skills=[],
            backstory="Already here.",
            reports_to=None,
            tools=None,
            picks_up=None,
        )

    data = yaml.safe_load(yaml_file.read_text())
    # Should still only have the original entry
    assert data["personas"]["existing"] == {"role": "dev"}


def test_append_to_company_yaml_exception(tmp_path):
    """Handles exceptions during YAML writing gracefully."""
    with (
        patch("opencompany.company.personas.os.path.join", return_value="/nonexistent/path.yaml"),
        patch("opencompany.company.personas.os.path.exists", return_value=True),
    ):
        # open() on a nonexistent path will raise
        _append_to_company_yaml("fail", "Fail", "Dev", "solver", [], "x", None, None, None)


# ---------------------------------------------------------------------------
# Sync wrappers
# ---------------------------------------------------------------------------
def test_hire_persona_sync_wrapper():
    """hire_persona_sync delegates to _hire_persona via _run_async."""
    with patch(
        "opencompany.company.personas._run_async",
        side_effect=mock_run_async("Hired Test (id=test)"),
    ) as mock:
        result = hire_persona_sync(
            persona_id="test",
            name="Test",
            role="Dev",
            persona_type="solver",
            skills=[],
            backstory="x",
        )
    assert "Hired Test" in result
    mock.assert_called_once()


def test_fire_persona_sync_wrapper():
    """fire_persona_sync delegates to _fire_persona via _run_async."""
    with patch(
        "opencompany.company.personas._run_async",
        side_effect=mock_run_async("Fired Test (test)"),
    ) as mock:
        result = fire_persona_sync(persona_id="test", reason="test")
    assert "Fired Test" in result
    mock.assert_called_once()


def test_list_personas_sync_wrapper():
    """list_personas_sync delegates to _list_personas via _run_async."""
    with patch(
        "opencompany.company.personas._run_async",
        side_effect=mock_run_async([{"id": "test"}]),
    ) as mock:
        result = list_personas_sync()
    assert result == [{"id": "test"}]
    mock.assert_called_once()


# ---------------------------------------------------------------------------
# _list_personas — rich return shape with workload + budget signals
# ---------------------------------------------------------------------------
async def test_list_personas_includes_workload_and_budget(persona_session):
    """_list_personas returns workload, budget, activity_state per persona.

    Regression guard: the tool ``list_team`` relies on these fields being
    present so LLM callers can make informed hire/assign/consolidate
    decisions. If ``_list_personas`` silently drops them, the tool output
    degrades to name-only and the guardrails become blind.
    """
    from opencompany.company.personas import _list_personas

    async with persona_session() as session:
        session.add(
            Persona(
                id="loaded-dev",
                name="Loaded Dev",
                role="Dev",
                type="solver",
                backstory="x",
                activity_state="working",
                daily_token_budget=10000,
                tokens_used_today=4500,
            )
        )
        session.add(
            Ticket(
                title="In-flight",
                status="in_progress",
                assigned_to="loaded-dev",
            )
        )
        session.add(
            Ticket(
                title="Queued",
                status="assigned",
                assigned_to="loaded-dev",
            )
        )
        # Done tickets do NOT count toward workload.
        session.add(
            Ticket(
                title="Shipped",
                status="done",
                assigned_to="loaded-dev",
            )
        )
        await session.commit()

    personas = await _list_personas()
    assert len(personas) == 1
    dev = personas[0]
    assert dev["id"] == "loaded-dev"
    assert dev["workload"] == 2  # assigned + in_progress
    assert dev["tokens_used_today"] == 4500
    assert dev["daily_token_budget"] == 10000
    assert dev["activity_state"] == "working"


async def test_list_personas_zero_workload_for_idle_persona(persona_session):
    """Personas with no assigned/in_progress tickets report workload=0."""
    from opencompany.company.personas import _list_personas

    async with persona_session() as session:
        session.add(
            Persona(
                id="idle-dev",
                name="Idle",
                role="Dev",
                type="solver",
                backstory="x",
                activity_state="idle",
                daily_token_budget=0,  # unlimited
            )
        )
        await session.commit()

    personas = await _list_personas()
    assert len(personas) == 1
    assert personas[0]["workload"] == 0
    assert personas[0]["tokens_used_today"] == 0
    assert personas[0]["daily_token_budget"] == 0
