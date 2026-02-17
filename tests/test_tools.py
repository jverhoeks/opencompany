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
    from opencompany.agents.tools.company import fire_persona, hire_persona, list_team

    assert callable(hire_persona)
    assert callable(fire_persona)
    assert callable(list_team)


def test_all_tools_registry():
    from opencompany.agents.tools import ALL_TOOLS

    assert len(ALL_TOOLS) == 9
    for name, func in ALL_TOOLS.items():
        assert callable(func), f"{name} is not callable"
