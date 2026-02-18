from strands import tool


@tool
def hire_persona(
    persona_id: str,
    name: str,
    role: str,
    persona_type: str,
    skills: str,
    backstory: str,
    reports_to: str = "",
    tools: str = "",
    picks_up: str = "",
) -> str:
    """Hire a new persona (create a new agent in the company).

    Args:
        persona_id: Unique ID for the persona (e.g. "junior-security-eng")
        name: Human name (e.g. "Alex Rivera")
        role: Job title (e.g. "Junior Security Engineer")
        persona_type: One of: solver, manager
        skills: Comma-separated skills (e.g. "security,python")
        backstory: Personality and background description
        reports_to: ID of the manager persona (optional)
        tools: Comma-separated tool names (optional, e.g. "read_file,write_file")
        picks_up: Comma-separated tags this persona picks up (optional)
    """
    from opencompany.company.personas import hire_persona_sync

    skill_list = [s.strip() for s in skills.split(",") if s.strip()]
    tool_list = [t.strip() for t in tools.split(",") if t.strip()] if tools else None
    picks_up_list = [p.strip() for p in picks_up.split(",") if p.strip()] if picks_up else None

    result = hire_persona_sync(
        persona_id=persona_id,
        name=name,
        role=role,
        persona_type=persona_type,
        skills=skill_list,
        backstory=backstory,
        reports_to=reports_to or None,
        tools=tool_list,
        picks_up=picks_up_list,
    )
    return result


@tool
def fire_persona(persona_id: str, reason: str = "") -> str:
    """Fire a persona and reassign their open tickets.

    Args:
        persona_id: ID of the persona to fire
        reason: Reason for firing
    """
    from opencompany.company.personas import fire_persona_sync

    return fire_persona_sync(persona_id=persona_id, reason=reason)


@tool
def list_team(reports_to: str = "") -> str:
    """List active personas in the company.

    Args:
        reports_to: Filter by manager ID (optional, empty = all)
    """
    from opencompany.company.personas import list_personas_sync

    personas = list_personas_sync(reports_to=reports_to or None)
    if not personas:
        return "No active personas found"
    lines = [f"- {p['name']} ({p['role']}) [{p['type']}] skills={p['skills']}" for p in personas]
    return "\n".join(lines)
