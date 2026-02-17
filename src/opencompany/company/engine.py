# src/opencompany/company/engine.py
"""Company engine: listens for events and orchestrates responses."""

import logging

from sqlalchemy import func, select

from opencompany.agents.runner import run_persona
from opencompany.company.taskboard import find_best_solver
from opencompany.events.bus import subscribe
from opencompany.models.db import Persona, Ticket
from opencompany.models.engine import async_session

logger = logging.getLogger(__name__)


async def _get_solvers_with_workload() -> list[dict]:
    """Get active solvers with their current ticket count."""
    async with async_session() as session:
        q = select(Persona).where(Persona.type == "solver", Persona.status == "active")
        result = await session.execute(q)
        solvers = result.scalars().all()

        solver_list = []
        for s in solvers:
            wq = select(func.count(Ticket.id)).where(
                Ticket.assigned_to == s.id,
                Ticket.status.in_(["assigned", "in_progress"]),
            )
            wresult = await session.execute(wq)
            workload = wresult.scalar() or 0
            solver_list.append(
                {
                    "id": s.id,
                    "skills": s.skills,
                    "picks_up": s.picks_up,
                    "workload": workload,
                }
            )

        return solver_list


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
    async with async_session() as session:
        ticket = await session.get(Ticket, ticket_id)
        if not ticket or ticket.status != "open":
            return

        solvers = await _get_solvers_with_workload()
        # Use picks_up tags for matching, fall back to skills
        for solver in solvers:
            solver["skills"] = solver["picks_up"] or solver["skills"]

        best = find_best_solver(tags=ticket.tags, solvers=solvers)
        if not best:
            logger.warning(f"No solver found for ticket #{ticket_id} tags={ticket.tags}")
            return

        ticket.assigned_to = best["id"]
        ticket.status = "assigned"
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
            "Investigate and solve this issue. When done, call update_ticket "
            "with the result and set status to 'review'."
        )

        await run_persona(persona, task)


async def _trigger_review(ticket_id: int):
    """Trigger reviewer for a completed ticket."""
    async with async_session() as session:
        ticket = await session.get(Ticket, ticket_id)
        if not ticket:
            return

        # Find the original creator (observer) to review
        reviewer = await session.get(Persona, ticket.created_by)
        if not reviewer:
            # Fall back to any manager
            q = select(Persona).where(Persona.type == "manager", Persona.status == "active")
            result = await session.execute(q)
            reviewer = result.scalars().first()

    if reviewer:
        task = f"""Review ticket #{ticket.id}: {ticket.title}

Solution: {ticket.result}

If the solution is good, call update_ticket with status='done'.
If not, call update_ticket with status='rejected' and explain what's wrong."""

        await run_persona(reviewer, task)


async def start_event_listener():
    """Start listening for events from the bus."""
    logger.info("Company engine event listener started")
    await subscribe(handle_event)
