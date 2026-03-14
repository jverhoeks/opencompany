"""Tests for Sprint 7: R1/R2 personas + SI4 propose_soul_update tool."""

from opencompany.company.config import load_company_config
from opencompany.company.trust import TOOL_TIER_REQUIREMENTS, filter_tools_by_tier


# ---------------------------------------------------------------------------
# R1/R2: Researcher and Marketer roles in YAML
# ---------------------------------------------------------------------------
class TestNewRoles:
    def test_researcher_role_exists(self):
        config = load_company_config()
        assert "researcher" in config.roles
        role = config.roles["researcher"]
        assert role["type"] == "solver"
        assert "web_search" in role["tools"]
        assert "web_fetch" in role["tools"]
        assert "research" in role.get("tag_match", [])

    def test_marketer_role_exists(self):
        config = load_company_config()
        assert "marketer" in config.roles
        role = config.roles["marketer"]
        assert role["type"] == "solver"
        assert "write_file" in role["tools"]
        assert "publish_file" in role["tools"]
        assert "marketing" in role.get("tag_match", [])
        # Marketer should NOT have hire or run_script
        assert "hire_persona" not in role["tools"]
        assert "run_script" not in role["tools"]


# ---------------------------------------------------------------------------
# SI4: propose_soul_update tool trust tier
# ---------------------------------------------------------------------------
class TestSoulToolTrust:
    def test_propose_soul_update_requires_lead(self):
        assert TOOL_TIER_REQUIREMENTS["propose_soul_update"] == "lead"

    def test_solver_cannot_propose_soul_update(self):
        allowed, denied = filter_tools_by_tier(["propose_soul_update"], "solver")
        assert "propose_soul_update" in denied

    def test_lead_can_propose_soul_update(self):
        allowed, denied = filter_tools_by_tier(["propose_soul_update"], "lead")
        assert "propose_soul_update" in allowed

    def test_read_soul_accessible_to_all(self):
        # read_soul has no tier requirement (defaults to external)
        allowed, denied = filter_tools_by_tier(["read_soul"], "external")
        assert "read_soul" in allowed


# ---------------------------------------------------------------------------
# Soul tools are registered
# ---------------------------------------------------------------------------
class TestSoulToolRegistration:
    def test_tools_registered(self):
        from opencompany.agents.tools import ALL_TOOLS

        assert "propose_soul_update" in ALL_TOOLS
        assert "read_soul" in ALL_TOOLS
