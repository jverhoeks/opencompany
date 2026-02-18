# src/opencompany/company/engine.py
"""Company engine: smart ticket routing and persona state tracking."""

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

# Tag-to-lead mapping for PM ticket routing
_LEAD_ROUTING: dict[str, str] = {
    "backend": "tech-lead",
    "frontend": "tech-lead",
    "architecture": "tech-lead",
    "technical": "tech-lead",
    "api": "tech-lead",
    "database": "tech-lead",
    "game-server": "tech-lead",
    "marketing": "marketing-lead",
    "content": "marketing-lead",
    "growth": "marketing-lead",
    "community": "marketing-lead",
    "sales": "marketing-lead",
    "sales-page": "marketing-lead",
    "website": "marketing-lead",
    "copy": "marketing-lead",
}


async def set_persona_state(persona_id: str, state: str) -> None:
    """Update a persona's activity_state (idle, working, blocked)."""
    async with async_session() as session:
        persona = await session.get(Persona, persona_id)
        if persona:
            persona.activity_state = state
            await session.commit()


async def handle_event(event_type: str, data: dict):
    """Handle events from the bus."""
    try:
        if event_type == "ticket.created":
            await _route_ticket(data["ticket_id"])
        elif event_type == "ticket.review":
            await _trigger_review(data["ticket_id"])
    except Exception:
        logger.exception("Error handling event %s: %s", event_type, data)


async def _route_ticket(ticket_id: int):
    """Route a ticket based on who created it.

    CEO-created -> PM (for breakdown)
    PM-created  -> relevant lead (by tags)
    Lead-created -> solver (skill matching)
    HR-tagged -> HR persona
    """
    logger.info("Routing ticket #%d", ticket_id)
    async with async_session() as session:
        ticket = await session.get(Ticket, ticket_id)
        if not ticket or ticket.status != "open":
            status = ticket.status if ticket else "N/A"
            logger.info("Ticket #%d skipped (status=%s)", ticket_id, status)
            return

        creator_id = ticket.created_by
        creator = await session.get(Persona, creator_id) if creator_id else None
        creator_type = creator.type if creator else None

        # HR-tagged tickets always go to HR
        if "hr" in ticket.tags or "hiring" in ticket.tags:
            target_id = "hr"
        # CEO tickets go to PM for breakdown
        elif creator_id == "ceo":
            target_id = "pm"
        # PM tickets go to relevant lead based on tags
        elif creator_id == "pm" or (
            creator_type == "manager" and creator_id not in ("tech-lead", "marketing-lead")
        ):
            target_id = _find_lead_for_tags(ticket.tags)
        # Lead/other tickets go to solver
        else:
            await _assign_to_solver(ticket, session)
            return

        # Assign to the target persona
        target = await session.get(Persona, target_id)
        if not target or target.status != "active":
            logger.warning("Target %s not available, falling back to solver", target_id)
            await _assign_to_solver(ticket, session)
            return

        ticket.assigned_to = target_id
        ticket.status = "assigned"
        log = WorkLog(persona_id=target_id, action="picked_up", ticket_id=ticket_id)
        session.add(log)
        await session.commit()
        logger.info("Routed ticket #%d to %s (%s)", ticket_id, target.name, target_id)

    _spawn_persona_task(
        target,
        _build_task_prompt(ticket),
        f"route-ticket-{ticket.id}-to-{target_id}",
    )


def _find_lead_for_tags(tags: list[str]) -> str:
    """Find the best lead for a set of tags."""
    for tag in tags:
        if tag.lower() in _LEAD_ROUTING:
            return _LEAD_ROUTING[tag.lower()]
    # Default to tech-lead for unrecognized tags
    return "tech-lead"


async def _assign_to_solver(ticket: Ticket, session) -> None:
    """Assign a ticket to the best available solver."""
    solvers = await _get_solvers_with_workload()
    logger.info(
        "Ticket #%d tags=%s | Available solvers: %s",
        ticket.id,
        ticket.tags,
        [(s["id"], s["picks_up"] or s["skills"]) for s in solvers],
    )
    for solver in solvers:
        solver["skills"] = solver["picks_up"] or solver["skills"]

    best = find_best_solver(tags=ticket.tags, solvers=solvers)
    if not best:
        logger.warning("No solver found for ticket #%d tags=%s", ticket.id, ticket.tags)
        return

    ticket.assigned_to = best["id"]
    ticket.status = "assigned"
    log = WorkLog(persona_id=best["id"], action="picked_up", ticket_id=ticket.id)
    session.add(log)
    await session.commit()
    logger.info("Assigned ticket #%d to solver %s", ticket.id, best["id"])

    persona = await session.get(Persona, best["id"])
    if persona:
        _spawn_persona_task(
            persona,
            _build_task_prompt(ticket),
            f"solve-ticket-{ticket.id}",
        )


def _build_task_prompt(ticket: Ticket) -> str:
    """Build a task prompt for a persona based on the ticket."""
    return (
        f"You have been assigned ticket #{ticket.id}: {ticket.title}\n\n"
        f"Description: {ticket.description}\n"
        f"Priority: {ticket.priority}\n"
        f"Tags: {', '.join(ticket.tags)}\n"
        f"Context: {ticket.context}\n\n"
        "Do the work for this ticket. If it involves writing code, documents, "
        "or any content, use write_file to save your output to the workspace. "
        "When done, call update_ticket with your result summary and set "
        "status to 'review'."
    )


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


async def _trigger_review(ticket_id: int):
    """Trigger reviewer for a completed ticket."""
    logger.info("Triggering review for ticket #%d", ticket_id)
    async with async_session() as session:
        ticket = await session.get(Ticket, ticket_id)
        if not ticket:
            logger.warning("Ticket #%d not found for review", ticket_id)
            return

        # Find the original creator to review
        reviewer = await session.get(Persona, ticket.created_by)
        if not reviewer:
            logger.info("Creator %s not found, falling back to manager", ticket.created_by)
            q = select(Persona).where(Persona.type == "manager", Persona.status == "active")
            result = await session.execute(q)
            reviewer = result.scalars().first()

    if reviewer:
        logger.info("Reviewer for ticket #%d: %s (%s)", ticket_id, reviewer.name, reviewer.id)
        task = (
            f"Review ticket #{ticket.id}: {ticket.title}\n\n"
            f"Solution: {ticket.result}\n\n"
            "If the solution is good, call update_ticket with status='done'.\n"
            "If not, call update_ticket with status='rejected' and explain what's wrong."
        )
        _spawn_persona_task(reviewer, task, f"review-ticket-{ticket.id}")


def _spawn_persona_task(persona: Persona, task: str, label: str):
    """Fire-and-forget an async persona run with state tracking."""

    async def _run():
        try:
            await set_persona_state(persona.id, "working")
            await run_persona(persona, task)
        except Exception:
            logger.exception("Background persona task %s failed", label)
            await set_persona_state(persona.id, "blocked")
        else:
            await set_persona_state(persona.id, "idle")

    t = asyncio.create_task(_run(), name=label)
    _running_tasks.add(t)
    t.add_done_callback(_running_tasks.discard)
    logger.info("Spawned background task: %s", label)


async def start_event_listener():
    """Start listening for events from the bus."""
    logger.info("Company engine event listener started")
    await subscribe(handle_event)
