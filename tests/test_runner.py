"""Tests for prompt building from config."""

from opencompany.agents.prompts import build_system_prompt
from opencompany.company.config import invalidate_cache, load_company_config
from opencompany.models.db import Persona


def test_build_system_prompt_from_config(tmp_path):
    """build_system_prompt uses role config for responsibilities/constraints."""
    invalidate_cache()
    yaml_file = tmp_path / "company.yaml"
    yaml_file.write_text("""
org_style: hierarchical
org_styles:
  hierarchical:
    routing: {}
roles:
  tech-lead:
    type: lead
    responsibilities: "Design architecture and review code."
    constraints: "Focus on runnable code only."
    tools: [create_ticket, read_file]
personas: {}
""")
    config = load_company_config(str(yaml_file))

    p = Persona(
        id="tech-lead",
        name="Dana Kim",
        role="Tech Lead",
        type="lead",
        skills=["python", "architecture"],
        backstory="15 years of engineering experience.",
    )
    prompt = build_system_prompt(p, config=config)
    assert "Dana Kim" in prompt
    assert "Tech Lead" in prompt
    assert "Design architecture" in prompt
    assert "runnable code" in prompt
    assert "tech-lead" in prompt
    invalidate_cache()


def test_build_system_prompt_solver(tmp_path):
    """Solver prompt includes role responsibilities."""
    invalidate_cache()
    yaml_file = tmp_path / "company.yaml"
    yaml_file.write_text("""
org_style: hierarchical
org_styles:
  hierarchical:
    routing: {}
roles:
  backend-dev:
    type: solver
    responsibilities: "Write backend code."
    constraints: "No cloud infra."
    tools: [read_file, write_file]
personas: {}
""")
    config = load_company_config(str(yaml_file))

    p = Persona(
        id="backend-dev",
        name="Jamie",
        role="Backend Dev",
        type="solver",
        skills=["python", "backend"],
        backstory="Fast coder.",
    )
    prompt = build_system_prompt(p, config=config)
    assert "Jamie" in prompt
    assert "Write backend code" in prompt
    assert "No cloud infra" in prompt
    invalidate_cache()


def test_build_system_prompt_fallback_no_role():
    """build_system_prompt works even without a matching role in config."""
    invalidate_cache()
    p = Persona(
        id="custom-worker",
        name="Alex",
        role="Custom Worker",
        type="solver",
        skills=["misc"],
        backstory="Does custom work.",
    )
    # No config passed — should still produce a valid prompt
    prompt = build_system_prompt(p)
    assert "Alex" in prompt
    assert "Custom Worker" in prompt
    assert "custom-worker" in prompt
    invalidate_cache()
