"""Tests for agent tools — schema checks and behavioral tests."""

from unittest.mock import patch


def test_ticket_tool_schema():
    from opencompany.agents.tools.tickets import create_ticket, list_tickets, update_ticket

    assert callable(create_ticket)
    assert callable(list_tickets)
    assert callable(update_ticket)


def test_code_tool_schema():
    from opencompany.agents.tools.code import grep_code, list_files, read_file

    assert callable(read_file)
    assert callable(list_files)
    assert callable(grep_code)


def test_company_tool_schema():
    from opencompany.agents.tools.company import (
        create_role,
        fire_persona,
        hire_persona,
        list_team,
    )

    assert callable(hire_persona)
    assert callable(fire_persona)
    assert callable(list_team)
    assert callable(create_role)


def test_all_tools_registry():
    from opencompany.agents.tools import ALL_TOOLS

    assert len(ALL_TOOLS) == 14
    for name, func in ALL_TOOLS.items():
        assert callable(func), f"{name} is not callable"


# ---------------------------------------------------------------------------
# Behavioral tests: code tools
# ---------------------------------------------------------------------------
def test_read_file_returns_contents(tmp_path):
    """read_file returns the contents of an existing file."""
    from opencompany.agents.tools.code import read_file

    test_file = tmp_path / "hello.py"
    test_file.write_text("print('hello')")

    # The @tool decorator wraps the function; call the underlying function
    result = read_file.__wrapped__(path=str(test_file))
    assert "print('hello')" in result


def test_read_file_missing_file():
    """read_file returns an error message for missing files."""
    from opencompany.agents.tools.code import read_file

    result = read_file.__wrapped__(path="/nonexistent/file.py")
    assert "Error" in result or "not found" in result


def test_list_files_shows_directory_contents(tmp_path):
    """list_files returns files in a directory."""
    from opencompany.agents.tools.code import list_files

    (tmp_path / "a.py").write_text("")
    (tmp_path / "b.py").write_text("")

    result = list_files.__wrapped__(directory=str(tmp_path))
    assert "a.py" in result
    assert "b.py" in result


def test_list_files_with_pattern(tmp_path):
    """list_files filters by glob pattern."""
    from opencompany.agents.tools.code import list_files

    (tmp_path / "code.py").write_text("")
    (tmp_path / "data.json").write_text("")

    result = list_files.__wrapped__(directory=str(tmp_path), pattern="*.py")
    assert "code.py" in result
    assert "data.json" not in result


def test_grep_code_finds_pattern(tmp_path):
    """grep_code finds a pattern in code files."""
    from opencompany.agents.tools.code import grep_code

    py_file = tmp_path / "example.py"
    py_file.write_text("def hello_world():\n    pass\n")

    result = grep_code.__wrapped__(pattern="hello_world", directory=str(tmp_path))
    assert "hello_world" in result


def test_grep_code_no_matches(tmp_path):
    """grep_code returns 'No matches' when pattern is not found."""
    from opencompany.agents.tools.code import grep_code

    py_file = tmp_path / "example.py"
    py_file.write_text("def foo():\n    pass\n")

    result = grep_code.__wrapped__(pattern="nonexistent_function", directory=str(tmp_path))
    assert "No matches" in result


# ---------------------------------------------------------------------------
# Behavioral tests: ticket tools (mock the sync wrappers)
# ---------------------------------------------------------------------------
def test_create_ticket_tool_calls_sync():
    """create_ticket tool parses tags and calls the sync wrapper."""
    from opencompany.agents.tools.tickets import create_ticket

    with patch("opencompany.company.taskboard.create_ticket_sync", return_value=42) as mock:
        result = create_ticket.__wrapped__(
            title="Fix auth bug",
            description="Auth is broken",
            priority="high",
            tags="security,backend",
        )

    assert "42" in result
    assert "Fix auth bug" in result
    mock.assert_called_once()
    call_kwargs = mock.call_args[1]
    assert call_kwargs["tags"] == ["security", "backend"]
    assert call_kwargs["priority"] == "high"


def test_list_tickets_tool_formats_output():
    """list_tickets tool formats ticket data into readable lines."""
    from opencompany.agents.tools.tickets import list_tickets

    mock_tickets = [
        {"id": 1, "title": "Bug A", "priority": "high", "assigned_to": "dev-1", "tags": []},
        {"id": 2, "title": "Bug B", "priority": "low", "assigned_to": None, "tags": []},
    ]

    with patch("opencompany.company.taskboard.list_tickets_sync", return_value=mock_tickets):
        result = list_tickets.__wrapped__(status="open")

    assert "#1" in result
    assert "Bug A" in result
    assert "unassigned" in result


def test_list_tickets_tool_empty():
    """list_tickets tool returns a message when no tickets match."""
    from opencompany.agents.tools.tickets import list_tickets

    with patch("opencompany.company.taskboard.list_tickets_sync", return_value=[]):
        result = list_tickets.__wrapped__(status="done")

    assert "No tickets" in result


def test_update_ticket_tool():
    """update_ticket tool calls the sync wrapper and returns confirmation."""
    from opencompany.agents.tools.tickets import update_ticket

    with patch("opencompany.company.taskboard.update_ticket_sync") as mock:
        result = update_ticket.__wrapped__(ticket_id=5, status="done", result="Fixed it")

    assert "5" in result
    assert "updated" in result
    mock.assert_called_once_with(ticket_id=5, status="done", result="Fixed it")


# ---------------------------------------------------------------------------
# Behavioral tests: company tools (mock the sync wrappers)
# ---------------------------------------------------------------------------
def test_hire_persona_tool():
    """hire_persona tool parses comma-separated skills."""
    from opencompany.agents.tools.company import hire_persona

    with patch(
        "opencompany.company.personas.hire_persona_sync",
        return_value="Hired Alex as Dev (id=new-dev)",
    ) as mock:
        result = hire_persona.__wrapped__(
            persona_id="new-dev",
            name="Alex",
            role="Dev",
            persona_type="solver",
            skills="python,backend",
            backstory="Great dev.",
        )

    assert "Hired Alex" in result
    call_kwargs = mock.call_args[1]
    assert call_kwargs["skills"] == ["python", "backend"]


def test_fire_persona_tool():
    """fire_persona tool calls the sync wrapper."""
    from opencompany.agents.tools.company import fire_persona

    with patch(
        "opencompany.company.personas.fire_persona_sync",
        return_value="Terminated Jamie (dev-1). Reason: Layoff",
    ):
        result = fire_persona.__wrapped__(persona_id="dev-1", reason="Layoff")

    assert "Terminated" in result


def test_list_team_tool_with_data():
    """list_team tool formats persona data into readable lines."""
    from opencompany.agents.tools.company import list_team

    mock_personas = [
        {"id": "dev-1", "name": "Jamie", "role": "Dev", "type": "solver", "skills": ["python"]},
    ]

    with patch("opencompany.company.personas.list_personas_sync", return_value=mock_personas):
        result = list_team.__wrapped__()

    assert "Jamie" in result
    assert "Dev" in result
    assert "solver" in result


def test_list_team_tool_empty():
    """list_team tool returns a message when no personas exist."""
    from opencompany.agents.tools.company import list_team

    with patch("opencompany.company.personas.list_personas_sync", return_value=[]):
        result = list_team.__wrapped__()

    assert "No active personas" in result
