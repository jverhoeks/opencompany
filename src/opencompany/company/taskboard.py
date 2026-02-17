"""Task board: ticket lifecycle, auto-assignment, sync wrappers for tool use."""

import asyncio
import logging

from sqlalchemy import select

from opencompany.models.db import Ticket
from opencompany.models.engine import async_session, get_main_loop

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from a sync context (e.g. agent tools running in threads)."""
    loop = get_main_loop()
    if loop and loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=60)
    # Fallback for non-threaded contexts (e.g. tests)
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


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
        logger.info(
            "Created ticket %d: %s (priority=%s, by=%s)",
            ticket.id,
            title,
            priority,
            created_by,
        )
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
        logger.debug("Listed %d tickets (status=%s, tags=%s)", len(tickets), status, tags)
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
            logger.warning("Update failed: ticket %d not found", ticket_id)
            return
        if status:
            ticket.status = status
        if result:
            ticket.result = result
        await session.commit()
        logger.info("Updated ticket %d (status=%s)", ticket_id, status)


def update_ticket_sync(**kwargs):
    return _run_async(_update_ticket(**kwargs))
