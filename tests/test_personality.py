"""Tests for the personality system."""

from opencompany.agents.prompts import build_system_prompt
from opencompany.company.config import CompanyConfig
from opencompany.models.db import Persona


def _make_persona(**kwargs) -> Persona:
    defaults = {
        "id": "test",
        "name": "Test",
        "role": "Test",
        "type": "solver",
        "backstory": "A test persona.",
    }
    defaults.update(kwargs)
    return Persona(**defaults)


def test_personality_injected_in_prompt():
    """Personality traits appear in system prompt."""
    personality = {
        "traits": ["bold", "creative"],
        "communication_style": "Direct and confident.",
        "quirks": ["Uses metaphors constantly"],
        "catchphrases": ["Let's go!", "Ship it."],
    }
    config = CompanyConfig(
        org_style="hierarchical",
        org_styles={},
        roles={
            "dev": {
                "type": "solver",
                "responsibilities": "Build things.",
                "personality": personality,
            }
        },
        personas={
            "dev": {
                "role": "dev",
                "personality": personality,
            }
        },
    )
    persona = _make_persona(id="dev", role="dev")
    prompt = build_system_prompt(persona, config)

    assert "PERSONALITY:" in prompt
    assert "bold, creative" in prompt
    assert "Direct and confident." in prompt
    assert "Uses metaphors constantly" in prompt
    assert "Let's go!" in prompt
    assert "Ship it." in prompt
    assert "Stay in character" in prompt


def test_personality_falls_back_to_role():
    """When persona has no personality, role-level personality is used."""
    personality = {
        "traits": ["pragmatic"],
        "communication_style": "Technical.",
    }
    config = CompanyConfig(
        org_style="hierarchical",
        org_styles={},
        roles={
            "dev": {
                "type": "solver",
                "responsibilities": "Code.",
                "personality": personality,
            }
        },
        personas={
            "dev": {"role": "dev"},  # no personality at persona level
        },
    )
    persona = _make_persona(id="dev", role="dev")
    prompt = build_system_prompt(persona, config)

    assert "PERSONALITY:" in prompt
    assert "pragmatic" in prompt
    assert "Technical." in prompt


def test_no_personality_no_crash():
    """Persona without personality config still gets a valid prompt."""
    config = CompanyConfig(
        org_style="hierarchical",
        org_styles={},
        roles={
            "dev": {
                "type": "solver",
                "responsibilities": "Code.",
            }
        },
        personas={},
    )
    persona = _make_persona(id="dev", role="dev")
    prompt = build_system_prompt(persona, config)

    assert "PERSONALITY:" not in prompt
    assert "You are Test" in prompt


def test_persona_personality_overrides_role():
    """Persona-level personality takes precedence over role-level."""
    config = CompanyConfig(
        org_style="hierarchical",
        org_styles={},
        roles={
            "dev": {
                "type": "solver",
                "responsibilities": "Code.",
                "personality": {
                    "traits": ["role-trait"],
                },
            }
        },
        personas={
            "dev": {
                "role": "dev",
                "personality": {
                    "traits": ["persona-trait"],
                },
            }
        },
    )
    persona = _make_persona(id="dev", role="dev")
    prompt = build_system_prompt(persona, config)

    assert "persona-trait" in prompt
    assert "role-trait" not in prompt
