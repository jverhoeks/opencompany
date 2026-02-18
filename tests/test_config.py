"""Tests for company config loading."""

import pytest

from opencompany.company.config import (
    CompanyConfig,
    add_role,
    get_org_routing,
    get_role,
    invalidate_cache,
    load_company_config,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear config cache before each test."""
    invalidate_cache()
    yield
    invalidate_cache()


def test_load_company_config(tmp_path):
    """load_company_config parses a valid company.yaml."""
    yaml_file = tmp_path / "company.yaml"
    yaml_file.write_text("""
org_style: hierarchical

org_styles:
  hierarchical:
    description: "Chain of command"
    routing:
      ceo: pm
      pm: lead
      lead: solver
    max_depth: 3

roles:
  ceo:
    builtin: true
    type: manager
    responsibilities: "Set strategic direction."
    constraints: "Do NOT break tickets into sub-tasks."
    tools: [create_ticket, list_tickets]
  hr:
    builtin: true
    type: manager
    responsibilities: "Handle hiring and firing."
    tools: [hire_persona, fire_persona]

personas:
  ceo:
    role: ceo
    name: "Morgan Hayes"
    backstory: "Visionary founder."
""")
    config = load_company_config(str(yaml_file))
    assert isinstance(config, CompanyConfig)
    assert config.org_style == "hierarchical"
    assert "ceo" in config.roles
    assert "hr" in config.roles
    assert config.roles["ceo"]["builtin"] is True
    assert config.roles["ceo"]["tools"] == ["create_ticket", "list_tickets"]


def test_get_role(tmp_path):
    """get_role returns a role definition from the config."""
    yaml_file = tmp_path / "company.yaml"
    yaml_file.write_text("""
org_style: hierarchical
org_styles:
  hierarchical:
    routing: {ceo: pm}
roles:
  ceo:
    builtin: true
    type: manager
    responsibilities: "Lead the company."
    tools: [create_ticket]
  pm:
    type: manager
    responsibilities: "Coordinate work."
    tools: [create_ticket, list_tickets]
personas:
  ceo:
    role: ceo
    name: "Boss"
    backstory: "The boss."
""")
    config = load_company_config(str(yaml_file))
    role = get_role("pm", config)
    assert role["type"] == "manager"
    assert "Coordinate" in role["responsibilities"]


def test_get_role_missing(tmp_path):
    """get_role raises KeyError for unknown roles."""
    yaml_file = tmp_path / "company.yaml"
    yaml_file.write_text("""
org_style: hierarchical
org_styles:
  hierarchical:
    routing: {}
roles:
  ceo:
    type: manager
    responsibilities: "Lead."
    tools: []
personas: {}
""")
    config = load_company_config(str(yaml_file))
    with pytest.raises(KeyError):
        get_role("nonexistent", config)


def test_get_org_routing(tmp_path):
    """get_org_routing returns routing dict for the active org style."""
    yaml_file = tmp_path / "company.yaml"
    yaml_file.write_text("""
org_style: dictator
org_styles:
  dictator:
    routing:
      ceo: solver
    max_depth: 1
  hierarchical:
    routing:
      ceo: pm
      pm: lead
      lead: solver
    max_depth: 3
roles: {}
personas: {}
""")
    config = load_company_config(str(yaml_file))
    routing = get_org_routing(config)
    assert routing == {"ceo": "solver"}


def test_load_config_missing_file():
    """load_company_config raises FileNotFoundError for missing files."""
    with pytest.raises(FileNotFoundError):
        load_company_config("/nonexistent/company.yaml")


def test_config_caching(tmp_path):
    """Config is cached on second load with same path."""
    yaml_file = tmp_path / "company.yaml"
    yaml_file.write_text("""
org_style: hierarchical
org_styles: {}
roles: {}
personas: {}
""")
    config1 = load_company_config(str(yaml_file))
    config2 = load_company_config(str(yaml_file))
    assert config1 is config2


def test_add_role(tmp_path):
    """add_role writes a new role to YAML and invalidates cache."""
    yaml_file = tmp_path / "company.yaml"
    yaml_file.write_text("""
org_style: hierarchical
org_styles: {}
roles:
  ceo:
    type: manager
    responsibilities: "Lead."
    tools: [create_ticket]
personas: {}
""")
    # Load to populate cache
    load_company_config(str(yaml_file))

    add_role(
        role_id="qa-engineer",
        role_type="solver",
        responsibilities="Write and run tests.",
        constraints="Focus on test coverage.",
        tools=["read_file", "write_file"],
        tag_match=["testing", "qa"],
        path=str(yaml_file),
    )

    # Cache should be invalidated, reload from file
    config = load_company_config(str(yaml_file))
    assert "qa-engineer" in config.roles
    role = config.roles["qa-engineer"]
    assert role["type"] == "solver"
    assert role["responsibilities"] == "Write and run tests."
    assert role["constraints"] == "Focus on test coverage."
    assert role["tools"] == ["read_file", "write_file"]
    assert role["tag_match"] == ["testing", "qa"]
    # Original role should still be there
    assert "ceo" in config.roles


def test_add_role_duplicate(tmp_path):
    """add_role raises ValueError for duplicate role IDs."""
    yaml_file = tmp_path / "company.yaml"
    yaml_file.write_text("""
org_style: hierarchical
org_styles: {}
roles:
  ceo:
    type: manager
    responsibilities: "Lead."
    tools: []
personas: {}
""")
    with pytest.raises(ValueError, match="already exists"):
        add_role(
            role_id="ceo",
            role_type="manager",
            responsibilities="Duplicate.",
            path=str(yaml_file),
        )


def test_load_real_company_yaml():
    """The actual company.yaml loads and has required sections."""
    config = load_company_config("config/company.yaml")
    assert config.org_style in config.org_styles
    assert "ceo" in config.roles
    assert "hr" in config.roles
    assert config.roles["ceo"].get("builtin") is True
    assert config.roles["hr"].get("builtin") is True
    # Only CEO + HR in personas section
    assert "ceo" in config.personas
    assert "hr" in config.personas
    # Roles have required fields
    for role_id, role in config.roles.items():
        assert "type" in role, f"Role {role_id} missing 'type'"
        assert "responsibilities" in role, f"Role {role_id} missing 'responsibilities'"
        assert "tools" in role, f"Role {role_id} missing 'tools'"
