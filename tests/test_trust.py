"""Tests for the trust tier system."""

from opencompany.company.trust import (
    TIERS,
    filter_tools_by_tier,
    get_trust_tier,
)
from opencompany.models.db import Persona


def _make_persona(**kwargs) -> Persona:
    defaults = {
        "id": "test",
        "name": "Test",
        "role": "Test",
        "type": "solver",
        "backstory": "",
    }
    defaults.update(kwargs)
    return Persona(**defaults)


# ---------------------------------------------------------------------------
# Tier derivation
# ---------------------------------------------------------------------------
def test_ceo_gets_full_tier():
    p = _make_persona(id="ceo", type="manager")
    assert get_trust_tier(p) == "full"


def test_hr_gets_full_tier():
    p = _make_persona(id="hr", type="manager")
    assert get_trust_tier(p) == "full"


def test_manager_gets_full_tier():
    p = _make_persona(id="pm", type="manager")
    assert get_trust_tier(p) == "full"


def test_solver_gets_solver_tier():
    p = _make_persona(id="backend-dev", type="solver")
    assert get_trust_tier(p) == "solver"


def test_lead_gets_lead_tier():
    p = _make_persona(id="tech-lead", type="lead")
    assert get_trust_tier(p) == "lead"


def test_unknown_type_gets_external_tier():
    p = _make_persona(id="guest", type="observer")
    assert get_trust_tier(p) == "external"


# ---------------------------------------------------------------------------
# Tool filtering
# ---------------------------------------------------------------------------
def test_full_tier_can_use_all_tools():
    tools = ["hire_persona", "fire_persona", "create_ticket", "write_file", "read_file"]
    allowed, denied = filter_tools_by_tier(tools, "full")
    assert allowed == tools
    assert denied == []


def test_solver_denied_dangerous_tools():
    tools = ["hire_persona", "fire_persona", "create_role", "write_file", "read_file"]
    allowed, denied = filter_tools_by_tier(tools, "solver")
    assert "hire_persona" in denied
    assert "fire_persona" in denied
    assert "create_role" in denied
    assert "write_file" in allowed
    assert "read_file" in allowed


def test_external_read_only():
    tools = [
        "hire_persona",
        "create_ticket",
        "write_file",
        "read_file",
        "list_files",
        "list_tickets",
        "list_team",
    ]
    allowed, denied = filter_tools_by_tier(tools, "external")
    assert set(allowed) == {"read_file", "list_files", "list_tickets", "list_team"}
    assert "hire_persona" in denied
    assert "create_ticket" in denied
    assert "write_file" in denied


def test_lead_tier_access():
    tools = ["create_ticket", "send_message", "hire_persona", "write_file", "read_file"]
    allowed, denied = filter_tools_by_tier(tools, "lead")
    assert "create_ticket" in allowed
    assert "send_message" in allowed
    assert "write_file" in allowed
    assert "read_file" in allowed
    assert "hire_persona" in denied


def test_tier_levels_ordered():
    assert TIERS["external"] < TIERS["solver"] < TIERS["lead"] < TIERS["full"]
