"""Soul tools: allow lead+ personas to propose updates to soul.md."""

from strands import tool


@tool
def propose_soul_update(
    proposed_content: str,
    rationale: str,
    persona_id: str = "",
) -> str:
    """Propose an update to soul.md (company operating principles).

    The update must pass validation gates:
    - Version number must be incremented
    - Maximum 3 rule changes per update
    - Protected rules (self-improvement rules) cannot be removed
    - soul.md must not exceed 200 lines

    Only available to lead trust tier and above.

    Args:
        proposed_content: The full proposed soul.md content (include version header)
        rationale: Why this change is needed (will be logged)
        persona_id: Your persona ID
    """
    from opencompany.company.soul import propose_update
    from opencompany.utils import _run_async

    accepted, reason = _run_async(propose_update(proposed_content, rationale, persona_id))
    if accepted:
        return f"Soul update accepted: {reason}"
    return f"Soul update rejected: {reason}"


@tool
def read_soul(
    persona_id: str = "",
) -> str:
    """Read the current soul.md operating principles.

    Args:
        persona_id: Your persona ID
    """
    from opencompany.company.soul import read_soul as _read

    content = _read()
    if not content:
        return "No soul.md found."
    return content
