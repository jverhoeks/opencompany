"""Tests for persona management (hire/fire/list)."""

from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from opencompany.company.personas import _fire_persona, _hire_persona, _list_personas
from opencompany.models.db import Persona


@pytest.fixture
async def persona_session(db_engine):
    """Provide an async session factory patched into personas module."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    with patch("opencompany.company.personas.async_session", factory):
        yield factory


async def test_hire_persona(persona_session, tmp_path):
    """Hiring creates a persona in the database."""
    with (
        patch("opencompany.company.personas.os.makedirs"),
        patch("opencompany.company.personas._append_to_company_yaml"),
    ):
        result = await _hire_persona(
            persona_id="new-dev",
            name="Alex",
            role="Developer",
            persona_type="solver",
            skills=["python", "backend"],
            backstory="A great developer.",
        )

    assert "Hired Alex as Developer" in result
    assert "new-dev" in result

    async with persona_session() as session:
        persona = await session.get(Persona, "new-dev")
        assert persona is not None
        assert persona.name == "Alex"
        assert persona.type == "solver"
        assert "python" in persona.skills


async def test_hire_duplicate_persona(persona_session):
    """Hiring a persona with an existing ID returns an error."""
    async with persona_session() as session:
        session.add(
            Persona(
                id="existing",
                name="Existing",
                role="Dev",
                type="solver",
                backstory="Already here.",
            )
        )
        await session.commit()

    with (
        patch("opencompany.company.personas.os.makedirs"),
        patch("opencompany.company.personas._append_to_company_yaml"),
    ):
        result = await _hire_persona(
            persona_id="existing",
            name="New",
            role="Dev",
            persona_type="solver",
            skills=[],
            backstory="Should not be created.",
        )

    assert "Error" in result
    assert "already exists" in result


async def test_fire_persona(persona_session):
    """Firing sets the persona status to fired."""
    async with persona_session() as session:
        session.add(
            Persona(
                id="dev-1",
                name="Jamie",
                role="Dev",
                type="solver",
                backstory="Good dev.",
            )
        )
        await session.commit()

    result = await _fire_persona("dev-1", reason="Layoff")
    assert "Fired Jamie" in result
    assert "Layoff" in result

    async with persona_session() as session:
        persona = await session.get(Persona, "dev-1")
        assert persona.status == "fired"


async def test_fire_nonexistent_persona(persona_session):
    """Firing a nonexistent persona returns an error."""
    result = await _fire_persona("ghost")
    assert "Error" in result
    assert "not found" in result


async def test_list_personas(persona_session):
    """List returns all active personas."""
    async with persona_session() as session:
        session.add(
            Persona(
                id="dev-1",
                name="Jamie",
                role="Dev",
                type="solver",
                skills=["python"],
                backstory="Good dev.",
            )
        )
        session.add(
            Persona(
                id="dev-2",
                name="Sam",
                role="Frontend Dev",
                type="solver",
                skills=["js"],
                backstory="UI expert.",
            )
        )
        await session.commit()

    personas = await _list_personas()
    assert len(personas) == 2
    ids = {p["id"] for p in personas}
    assert ids == {"dev-1", "dev-2"}


async def test_list_personas_excludes_fired(persona_session):
    """Fired personas are not included in list."""
    async with persona_session() as session:
        session.add(
            Persona(
                id="active",
                name="Active",
                role="Dev",
                type="solver",
                backstory="Still here.",
            )
        )
        session.add(
            Persona(
                id="fired-dev",
                name="Fired",
                role="Dev",
                type="solver",
                status="fired",
                backstory="Gone.",
            )
        )
        await session.commit()

    personas = await _list_personas()
    assert len(personas) == 1
    assert personas[0]["id"] == "active"


async def test_list_personas_filter_by_reports_to(persona_session):
    """List can filter by reports_to."""
    async with persona_session() as session:
        session.add(
            Persona(
                id="ceo",
                name="CEO",
                role="CEO",
                type="manager",
                backstory="Boss.",
            )
        )
        session.add(
            Persona(
                id="dev-1",
                name="Jamie",
                role="Dev",
                type="solver",
                reports_to="ceo",
                backstory="Reports to CEO.",
            )
        )
        session.add(
            Persona(
                id="dev-2",
                name="Sam",
                role="Dev",
                type="solver",
                backstory="No manager.",
            )
        )
        await session.commit()

    personas = await _list_personas(reports_to="ceo")
    assert len(personas) == 1
    assert personas[0]["id"] == "dev-1"
