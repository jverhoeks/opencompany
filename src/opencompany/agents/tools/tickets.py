import logging

from strands import tool

logger = logging.getLogger(__name__)


@tool
def create_ticket(
    title: str,
    description: str = "",
    priority: str = "medium",
    tags: str = "",
    context: str = "",
    created_by: str = "agent",
) -> str:
    """Create a new ticket on the task board.

    Args:
        title: Short title describing the issue or task
        description: Detailed description of what needs to be done
        priority: One of: critical, high, medium, low
        tags: Comma-separated tags (e.g. "security,backend")
        context: Relevant file paths, code snippets, or references
        created_by: Your persona ID (e.g. "ceo", "cto")
    """
    from opencompany.company.taskboard import create_ticket_sync

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    context_dict = {"raw": context} if context else {}

    ticket_id = create_ticket_sync(
        title=title,
        description=description,
        priority=priority,
        tags=tag_list,
        context=context_dict,
        created_by=created_by,
    )
    logger.info(
        "[%s] created ticket #%d: %s [%s] tags=%s",
        created_by,
        ticket_id,
        title,
        priority,
        tag_list,
    )
    return f"Ticket #{ticket_id} created: {title} [{priority}]"


@tool
def list_tickets(status: str = "open", tags: str = "") -> str:
    """List tickets from the task board.

    Args:
        status: Filter by status (open, assigned, in_progress, review, done)
        tags: Comma-separated tags to filter by
    """
    from opencompany.company.taskboard import list_tickets_sync

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    tickets = list_tickets_sync(status=status, tags=tag_list)
    if not tickets:
        return f"No tickets with status={status}"
    lines = [
        f"#{t['id']} [{t['priority']}] {t['title']} (-> {t['assigned_to'] or 'unassigned'})"
        for t in tickets
    ]
    return "\n".join(lines)


@tool
def update_ticket(ticket_id: int, status: str = "", result: str = "") -> str:
    """Update a ticket's status or add a result.

    Args:
        ticket_id: The ticket ID to update
        status: New status (assigned, in_progress, review, done, rejected)
        result: Solution or output to attach to the ticket
    """
    from opencompany.company.taskboard import update_ticket_sync

    update_ticket_sync(ticket_id=ticket_id, status=status or None, result=result or None)
    logger.info("[tool] update_ticket #%d → status=%s", ticket_id, status or "(unchanged)")
    return f"Ticket #{ticket_id} updated"
