from opencompany.agents.prompts import build_system_prompt
from opencompany.models.db import Persona


def test_build_system_prompt():
    p = Persona(
        id="security-analyst",
        name="Sarah Chen",
        role="Security Analyst",
        type="solver",
        skills=["security"],
        backstory="Senior security engineer with 10 years experience.",
    )
    prompt = build_system_prompt(p)
    assert "Sarah Chen" in prompt
    assert "Security Analyst" in prompt
    assert "solver" in prompt
    assert "Senior security engineer" in prompt


def test_build_system_prompt_solver():
    p = Persona(
        id="dev-1",
        name="Jamie",
        role="Backend Dev",
        type="solver",
        skills=["python", "backend"],
        backstory="Fast coder.",
    )
    prompt = build_system_prompt(p)
    assert "solver" in prompt
    assert "Jamie" in prompt
    assert "python" in prompt
