"""Coverage tests for agents/tools/company.py — fire_persona and create_role tool edges."""

from unittest.mock import patch


def test_create_role_tool_success():
    """create_role calls add_role and returns success message."""
    from opencompany.agents.tools.company import create_role

    with patch("opencompany.company.config.add_role") as mock:
        result = create_role.__wrapped__(
            role_id="qa-engineer",
            role_type="solver",
            responsibilities="Test everything",
            constraints="Only test code",
            tools="read_file,grep_code",
            tag_match="testing,qa",
            routes_to="solver",
        )

    assert "qa-engineer" in result
    assert "created successfully" in result
    mock.assert_called_once_with(
        role_id="qa-engineer",
        role_type="solver",
        responsibilities="Test everything",
        constraints="Only test code",
        tools=["read_file", "grep_code"],
        tag_match=["testing", "qa"],
        routes_to="solver",
    )


def test_create_role_tool_no_optional_fields():
    """create_role passes None for empty optional fields."""
    from opencompany.agents.tools.company import create_role

    with patch("opencompany.company.config.add_role") as mock:
        result = create_role.__wrapped__(
            role_id="basic-role",
            role_type="solver",
            responsibilities="Do stuff",
        )

    assert "created successfully" in result
    mock.assert_called_once_with(
        role_id="basic-role",
        role_type="solver",
        responsibilities="Do stuff",
        constraints="",
        tools=None,
        tag_match=None,
        routes_to=None,
    )


def test_create_role_tool_already_exists():
    """create_role returns error when role already exists."""
    from opencompany.agents.tools.company import create_role

    with patch(
        "opencompany.company.config.add_role",
        side_effect=ValueError("Role 'existing' already exists"),
    ):
        result = create_role.__wrapped__(
            role_id="existing",
            role_type="solver",
            responsibilities="x",
        )

    assert "Error" in result
    assert "already exists" in result


def test_create_role_tool_file_not_found():
    """create_role returns error when company.yaml is missing."""
    from opencompany.agents.tools.company import create_role

    with patch(
        "opencompany.company.config.add_role",
        side_effect=FileNotFoundError("company.yaml not found"),
    ):
        result = create_role.__wrapped__(
            role_id="new-role",
            role_type="solver",
            responsibilities="x",
        )

    assert "Error" in result


def test_fire_persona_tool_delegates():
    """fire_persona tool calls fire_persona_sync and returns result."""
    from opencompany.agents.tools.company import fire_persona

    with patch(
        "opencompany.company.personas.fire_persona_sync",
        return_value="Fired Alex (alex-dev). Reason: Performance",
    ) as mock:
        result = fire_persona.__wrapped__(persona_id="alex-dev", reason="Performance")

    assert "Fired Alex" in result
    mock.assert_called_once_with(persona_id="alex-dev", reason="Performance")


def test_fire_persona_tool_default_reason():
    """fire_persona tool uses empty reason by default."""
    from opencompany.agents.tools.company import fire_persona

    with patch(
        "opencompany.company.personas.fire_persona_sync",
        return_value="Fired Bob (bob). Reason: ",
    ) as mock:
        result = fire_persona.__wrapped__(persona_id="bob")

    assert "Fired Bob" in result
    mock.assert_called_once_with(persona_id="bob", reason="")


def test_hire_persona_tool_with_tools_and_picks_up():
    """hire_persona parses tools and picks_up comma-separated strings."""
    from opencompany.agents.tools.company import hire_persona

    with patch(
        "opencompany.company.personas.hire_persona_sync",
        return_value="Hired Dev (id=dev)",
    ) as mock:
        hire_persona.__wrapped__(
            persona_id="dev",
            name="Dev",
            role="Developer",
            persona_type="solver",
            skills="python,go",
            backstory="Good dev",
            reports_to="ceo",
            tools="read_file,write_file",
            picks_up="backend,api",
        )

    call_kwargs = mock.call_args[1]
    assert call_kwargs["tools"] == ["read_file", "write_file"]
    assert call_kwargs["picks_up"] == ["backend", "api"]
    assert call_kwargs["reports_to"] == "ceo"


def test_list_team_with_reports_to():
    """list_team passes reports_to filter."""
    from opencompany.agents.tools.company import list_team

    mock_data = [
        {"id": "dev-1", "name": "Dev", "role": "Dev", "type": "solver", "skills": ["py"]},
    ]

    with patch(
        "opencompany.company.personas.list_personas_sync",
        return_value=mock_data,
    ) as mock:
        result = list_team.__wrapped__(reports_to="ceo")

    mock.assert_called_once_with(reports_to="ceo")
    assert "Dev" in result
