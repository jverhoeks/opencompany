"""Task board: ticket lifecycle, auto-assignment, sync wrappers for tool use."""

import logging
from datetime import UTC, datetime

from sqlalchemy import select

from opencompany.events.bus import publish
from opencompany.models.db import Ticket, WorkLog
from opencompany.models.engine import async_session
from opencompany.utils import _run_async

logger = logging.getLogger(__name__)


def _fuzzy_tag_score(solver_tags: set[str], ticket_tags: set[str]) -> float:
    """Score a solver against ticket tags using exact + substring matching.

    Exact match = 1.0 per tag, substring match = 0.5 per tag.
    E.g. solver skill "frontend" partially matches ticket tag "frontend-dev",
    and "design" partially matches "web-design".
    """
    score = 0.0
    for tt in ticket_tags:
        if tt in solver_tags:
            score += 1.0
            continue
        # Substring: does any solver tag appear inside ticket tag or vice-versa?
        for st in solver_tags:
            if st in tt or tt in st:
                score += 0.5
                break
    return score


def find_best_solver(tags: list[str], solvers: list[dict]) -> dict | None:
    """Find the best solver for a ticket based on skill overlap and workload.

    Uses fuzzy tag matching (exact + substring) and falls back to the least
    busy solver if no match is found.
    """
    if not solvers:
        return None

    ticket_tags = {t.lower() for t in tags}
    candidates = []
    for solver in solvers:
        solver_tags = {s.lower() for s in solver["skills"]}
        score = _fuzzy_tag_score(solver_tags, ticket_tags)
        logger.debug(
            "Solver scoring: %s score=%.1f workload=%d (skills=%s vs tags=%s)",
            solver["id"],
            score,
            solver["workload"],
            solver["skills"],
            tags,
        )
        if score > 0:
            candidates.append((score, solver["workload"], solver))

    if candidates:
        # Sort by score (desc), then workload (asc)
        candidates.sort(key=lambda x: (-x[0], x[1]))
        best = candidates[0]
        logger.debug("Best solver candidate: %s (score=%.1f)", best[2]["id"], best[0])
        return candidates[0][2]

    # Fallback: assign to the least busy solver
    logger.info("No tag match for %s, falling back to least busy solver", tags)
    return min(solvers, key=lambda s: s["workload"])


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
        logger.info("Updated ticket %d (status=%s)", ticket_id, status)

        # Trigger review flow when a solver submits for review
        if status == "review":
            await publish("ticket.review", {"ticket_id": ticket_id})


def update_ticket_sync(**kwargs):
    return _run_async(_update_ticket(**kwargs))
