"""Task board: ticket lifecycle, auto-assignment, sync wrappers for tool use."""

import logging
from datetime import UTC, datetime

from sqlalchemy import select

from opencompany.events.bus import publish
from opencompany.models.db import Ticket, WorkLog
from opencompany.models.engine import async_session
from opencompany.utils import _run_async

logger = logging.getLogger(__name__)


def find_best_solver(tags: list[str], solvers: list[dict]) -> dict | None:
    """Find the best solver for a ticket based on skill overlap and workload."""
    candidates = []
    for solver in solvers:
        overlap = len(set(solver["skills"]) & set(tags))
        if overlap > 0:
            candidates.append((overlap, solver["workload"], solver))

    if not candidates:
        return None

    # Sort by skill overlap (desc), then workload (asc)
    candidates.sort(key=lambda x: (-x[0], x[1]))
    return candidates[0][2]


async def _create_ticket(
    title: str,
    description: str,
    priority: str,
    tags: list,
    context: dict,
    created_by: str,
) -> int:
    async with async_session() as session:
        ticket = Ticket(
            title=title,
            description=description,
            priority=priority,
            tags=tags,
            context=context,
            created_by=created_by,
        )
        session.add(ticket)
        log = WorkLog(persona_id=created_by, action="created", ticket_id=ticket.id)
        session.add(log)
        await session.commit()
        await session.refresh(ticket)
        await publish("ticket.created", {"ticket_id": ticket.id})
        return ticket.id


def create_ticket_sync(**kwargs) -> int:
    """Sync wrapper for use in @tool functions."""
    return _run_async(_create_ticket(**kwargs))


async def _list_tickets(status: str, tags: list) -> list[dict]:
    async with async_session() as session:
        q = select(Ticket).where(Ticket.status == status)
        result = await session.execute(q)
        tickets = result.scalars().all()
        if tags:
            tickets = [t for t in tickets if set(tags) & set(t.tags)]
        return [
            {
                "id": t.id,
                "title": t.title,
                "priority": t.priority,
                "assigned_to": t.assigned_to,
                "tags": t.tags,
            }
            for t in tickets
        ]


def list_tickets_sync(**kwargs) -> list[dict]:
    return _run_async(_list_tickets(**kwargs))


async def _update_ticket(ticket_id: int, status: str | None = None, result: str | None = None):
    async with async_session() as session:
        ticket = await session.get(Ticket, ticket_id)
        if not ticket:
            logger.warning("Ticket #%d not found for update", ticket_id)
            return f"Error: ticket #{ticket_id} not found"
        if status:
            ticket.status = status
            log = WorkLog(
                persona_id=ticket.created_by or "system",
                action=status,
                ticket_id=ticket_id,
            )
            session.add(log)
        if result:
            ticket.result = result
        ticket.updated_at = datetime.now(UTC)
        await session.commit()


def update_ticket_sync(**kwargs):
    return _run_async(_update_ticket(**kwargs))
