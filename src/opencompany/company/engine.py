# src/opencompany/company/engine.py
"""Company engine: listens for events and orchestrates responses."""

import asyncio
import logging

from sqlalchemy import and_, func, select

from opencompany.agents.runner import run_persona
from opencompany.company.taskboard import find_best_solver
from opencompany.events.bus import subscribe
from opencompany.models.db import Persona, Ticket, WorkLog
from opencompany.models.engine import async_session

logger = logging.getLogger(__name__)

# Track background persona tasks so we don't lose exceptions silently
_running_tasks: set[asyncio.Task] = set()


async def _get_solvers_with_workload() -> list[dict]:
    """Get active solvers with their current ticket count."""
    async with async_session() as session:
        q = (
            select(
                Persona.id,
                Persona.skills,
                Persona.picks_up,
                func.count(Ticket.id).label("workload"),
            )
            .outerjoin(
                Ticket,
                and_(
                    Ticket.assigned_to == Persona.id,
                    Ticket.status.in_(["assigned", "in_progress"]),
                ),
            )
            .where(Persona.type == "solver", Persona.status == "active")
            .group_by(Persona.id, Persona.skills, Persona.picks_up)
        )
        result = await session.execute(q)
        return [
            {
                "id": row.id,
                "skills": row.skills,
                "picks_up": row.picks_up,
                "workload": row.workload,
            }
            for row in result.all()
        ]


async def handle_event(event_type: str, data: dict):
    """Handle events from the bus."""
    try:
        if event_type == "ticket.created":
            await _auto_assign_ticket(data["ticket_id"])
        elif event_type == "ticket.review":
            await _trigger_review(data["ticket_id"])
    except Exception:
        logger.exception("Error handling event %s: %s", event_type, data)


async def _auto_assign_ticket(ticket_id: int):
    """Auto-assign a ticket to the best available solver."""
    logger.info("Auto-assigning ticket #%d", ticket_id)
    async with async_session() as session:
        ticket = await session.get(Ticket, ticket_id)
        if not ticket or ticket.status != "open":
            status = ticket.status if ticket else "N/A"
            logger.info("Ticket #%d skipped (status=%s)", ticket_id, status)
            return

        solvers = await _get_solvers_with_workload()
        logger.info(
            "Ticket #%d tags=%s | Available solvers: %s",
            ticket_id,
            ticket.tags,
            [(s["id"], s["picks_up"] or s["skills"]) for s in solvers],
        )
        # Use picks_up tags for matching, fall back to skills
        for solver in solvers:
            solver["skills"] = solver["picks_up"] or solver["skills"]

        best = find_best_solver(tags=ticket.tags, solvers=solvers)
        if not best:
            logger.warning("No solver found for ticket #%d tags=%s", ticket_id, ticket.tags)
            return

        ticket.assigned_to = best["id"]
        ticket.status = "assigned"
        log = WorkLog(persona_id=best["id"], action="picked_up", ticket_id=ticket_id)
        session.add(log)
        await session.commit()
        logger.info(f"Assigned ticket #{ticket_id} to {best['id']}")

        # Trigger the solver to work on it
        persona = await session.get(Persona, best["id"])

    if persona:
        task = (
            f"You have been assigned ticket #{ticket.id}: {ticket.title}\n\n"
            f"Description: {ticket.description}\n"
            f"Priority: {ticket.priority}\n"
            f"Context: {ticket.context}\n\n"
            "Do the work for this ticket. If it involves writing code, documents, "
            "or any content, use write_file to save your output to the workspace. "
            "When done, call update_ticket with your result summary and set "
            "status to 'review'."
        )

        _spawn_persona_task(persona, task, f"solve-ticket-{ticket.id}")


async def _trigger_review(ticket_id: int):
    """Trigger reviewer for a completed ticket."""
    logger.info("Triggering review for ticket #%d", ticket_id)
    async with async_session() as session:
        ticket = await session.get(Ticket, ticket_id)
        if not ticket:
            logger.warning("Ticket #%d not found for review", ticket_id)
            return

        # Find the original creator (observer) to review
        reviewer = await session.get(Persona, ticket.created_by)
        if not reviewer:
            logger.info("Creator %s not found, falling back to manager", ticket.created_by)
            # Fall back to any manager
            q = select(Persona).where(Persona.type == "manager", Persona.status == "active")
            result = await session.execute(q)
            reviewer = result.scalars().first()

    if reviewer:
        logger.info("Reviewer for ticket #%d: %s (%s)", ticket_id, reviewer.name, reviewer.id)
        task = f"""Review ticket #{ticket.id}: {ticket.title}

Solution: {ticket.result}

If the solution is good, call update_ticket with status='done'.
If not, call update_ticket with status='rejected' and explain what's wrong."""

        _spawn_persona_task(reviewer, task, f"review-ticket-{ticket.id}")


def _spawn_persona_task(persona: Persona, task: str, label: str):
    """Fire-and-forget an async persona run without blocking the event loop."""

    async def _run():
        try:
            await run_persona(persona, task)
        except Exception:
            logger.exception("Background persona task %s failed", label)

    t = asyncio.create_task(_run(), name=label)
    _running_tasks.add(t)
    t.add_done_callback(_running_tasks.discard)
    logger.info("Spawned background task: %s", label)


async def start_event_listener():
    """Start listening for events from the bus."""
    logger.info("Company engine event listener started")
    await subscribe(handle_event)
