"""Policy tools: allow personas to create, approve, list, and read policy documents."""

from strands import tool


@tool
def write_policy(
    title: str,
    content: str,
    tags: list[str] = [],  # noqa: B006
    applies_to: list[str] = [],  # noqa: B006
    persona_id: str = "",
) -> str:
    """Create a new policy document (starts as draft, needs approval).

    Use this to establish coding standards, design guidelines, process docs, etc.

    Args:
        title: Policy title (e.g. "API Design Guidelines")
        content: Full policy text in markdown
        tags: Topic tags (e.g. ["engineering", "api"])
        applies_to: Who this policy targets — role IDs, persona IDs, or ["*"] for everyone
        persona_id: Your persona ID (the author)
    """
    from opencompany.company.policy import create_policy
    from opencompany.utils import _run_async

    policy_id = _run_async(
        create_policy(
            author_id=persona_id,
            title=title,
            content=content,
            tags=tags,
            applies_to=applies_to,
        )
    )
    return (
        f"Policy #{policy_id} '{title}' created as draft. Needs approval from a manager or lead."
    )


@tool
def approve_policy(
    policy_id: int,
    persona_id: str = "",
) -> str:
    """Approve a draft policy document, making it active for the team.

    Only managers and leads can approve policies.

    Args:
        policy_id: ID of the policy to approve
        persona_id: Your persona ID (the approver)
    """
    from opencompany.company.policy import approve_policy as _approve
    from opencompany.utils import _run_async

    try:
        policy = _run_async(_approve(policy_id, persona_id))
        title = policy["title"]
        return (
            f"Policy #{policy_id} '{title}' approved. "
            "It will now appear in relevant personas' prompts."
        )
    except (PermissionError, ValueError) as e:
        return f"Cannot approve policy: {e}"


@tool
def list_policies(
    status: str = "",
    tag: str = "",
    persona_id: str = "",
) -> str:
    """List policy documents with optional filters.

    Args:
        status: Filter by status (draft, approved, rejected) — empty for all
        tag: Filter by tag — empty for all
        persona_id: Your persona ID
    """
    from opencompany.company.policy import list_policies as _list
    from opencompany.utils import _run_async

    policies = _run_async(_list(status=status or None, tag=tag or None))
    if not policies:
        return "No policies found."

    lines = []
    for p in policies:
        tags = ", ".join(p["tags"]) if p["tags"] else "none"
        targets = ", ".join(p["applies_to"]) if p["applies_to"] else "none"
        lines.append(
            f"#{p['id']} [{p['status']}] {p['title']} "
            f"(by {p['author_id']}, tags: {tags}, applies to: {targets})"
        )
    return "\n".join(lines)


@tool
def read_policy(
    policy_id: int,
    persona_id: str = "",
) -> str:
    """Read the full content of a policy document.

    Args:
        policy_id: ID of the policy to read
        persona_id: Your persona ID
    """
    from opencompany.company.policy import get_policy
    from opencompany.utils import _run_async

    policy = _run_async(get_policy(policy_id))
    if not policy:
        return f"Policy #{policy_id} not found."

    tags = ", ".join(policy["tags"]) if policy["tags"] else "none"
    targets = ", ".join(policy["applies_to"]) if policy["applies_to"] else "none"
    return (
        f"# {policy['title']}\n"
        f"Status: {policy['status']} | Author: {policy['author_id']} | "
        f"Approved by: {policy['approved_by'] or 'pending'}\n"
        f"Tags: {tags} | Applies to: {targets}\n\n"
        f"{policy['content']}"
    )
