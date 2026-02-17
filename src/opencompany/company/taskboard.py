"""Task board: ticket lifecycle, auto-assignment, sync wrappers for tool use."""

import asyncio

from sqlalchemy import select

from opencompany.models.db import Ticket
from opencompany.models.engine import async_session


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
        await session.commit()
        await session.refresh(ticket)
        return ticket.id


def create_ticket_sync(**kwargs) -> int:
    """Sync wrapper for use in @tool functions."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_create_ticket(**kwargs))
    finally:
        loop.close()


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
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_list_tickets(**kwargs))
    finally:
        loop.close()


async def _update_ticket(ticket_id: int, status: str | None = None, result: str | None = None):
    async with async_session() as session:
        ticket = await session.get(Ticket, ticket_id)
        if not ticket:
            return
        if status:
            ticket.status = status
        if result:
            ticket.result = result
        await session.commit()


def update_ticket_sync(**kwargs):
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_update_ticket(**kwargs))
    finally:
        loop.close()
