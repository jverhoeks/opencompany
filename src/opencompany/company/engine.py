"""Company engine: config-driven ticket routing and persona state tracking."""

import asyncio
import logging

from sqlalchemy import and_, func, select

from opencompany.agents.runner import run_persona
from opencompany.company.config import load_company_config
from opencompany.company.taskboard import find_best_solver
from opencompany.events.bus import subscribe
from opencompany.models.db import Persona, Ticket, WorkLog
from opencompany.models.engine import async_session

logger = logging.getLogger(__name__)

# Track background persona tasks so we don't lose exceptions silently
_running_tasks: set[asyncio.Task] = set()


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
    """Route a ticket based on org style routing rules and role config.

    Reads routing from company config:
    - Look up creator's role type
    - Apply org_style routing: ceo->pm, pm->lead, lead->solver, etc.
    - For 'lead' targets, match ticket tags to role tag_match
    - For 'solver' targets, use find_best_solver
    - HR-tagged tickets always go to HR
    """
    logger.info("Routing ticket #%d", ticket_id)

    try:
        config = load_company_config()
    except FileNotFoundError:
        logger.warning("No company config, cannot route ticket #%d", ticket_id)
        return

    routing = config.org_styles.get(config.org_style, {}).get("routing", {})

    async with async_session() as session:
        ticket = await session.get(Ticket, ticket_id)
        if not ticket or ticket.status != "open":
            status = ticket.status if ticket else "N/A"
            logger.info("Ticket #%d skipped (status=%s)", ticket_id, status)
            return

        creator_id = ticket.created_by
        creator = await session.get(Persona, creator_id) if creator_id else None

        # HR-tagged tickets always go to HR
        if "hr" in ticket.tags or "hiring" in ticket.tags:
            target_id = "hr"
        else:
            target_type = _get_routing_target(creator, config, routing)

            if target_type == "solver":
                await _assign_to_solver(ticket, session)
                return
            elif target_type in ("lead", "circle"):
                target_id = _find_lead_for_tags(ticket.tags, config)
                if not target_id:
                    await _assign_to_solver(ticket, session)
                    return
            else:
                # target_type is a specific role ID (e.g. "pm")
                target_id = target_type

        if not target_id:
            logger.warning(
                "No routing target for ticket #%d, falling back to solver",
                ticket_id,
            )
            await _assign_to_solver(ticket, session)
            return

        target = await session.get(Persona, target_id)
        if not target or target.status != "active":
            logger.warning(
                "Target %s not available, falling back to solver",
                target_id,
            )
            await _assign_to_solver(ticket, session)
            return

        ticket.assigned_to = target_id
        ticket.status = "assigned"
        log = WorkLog(persona_id=target_id, action="picked_up", ticket_id=ticket_id)
        session.add(log)
        await session.commit()
        logger.info(
            "Routed ticket #%d to %s (%s)",
            ticket_id,
            target.name,
            target_id,
        )

    _spawn_persona_task(
        target,
        _build_task_prompt(ticket),
        f"route-ticket-{ticket.id}-to-{target_id}",
    )


def _get_routing_target(
    creator: Persona | None,
    config,
    routing: dict[str, str],
) -> str:
    """Determine where a ticket should go based on creator's role."""
    if not creator:
        return "solver"

    # Check routing by creator's persona ID first
    if creator.id in routing:
        return routing[creator.id]

    # Check role config for routes_to
    creator_role_config = config.roles.get(creator.id, {})
    routes_to = creator_role_config.get("routes_to")
    if routes_to:
        return routes_to

    # Check routing table by type
    role_type = creator_role_config.get("type", creator.type)
    if role_type in routing:
        return routing[role_type]

    # Leads route to solver by default
    if role_type == "lead":
        return "solver"

    return "solver"


def _find_lead_for_tags(tags: list[str], config) -> str | None:
    """Find the best lead/persona for a set of tags using fuzzy role tag_match.

    Exact match = 1.0, substring match = 0.5 (e.g. "design" in "web-design").
    """
    best_match = None
    best_score = 0.0

    ticket_tags = {t.lower() for t in tags}

    for role_id, role in config.roles.items():
        tag_match = role.get("tag_match", [])
        if not tag_match:
            continue
        role_tags = {tm.lower() for tm in tag_match}
        score = 0.0
        for tt in ticket_tags:
            if tt in role_tags:
                score += 1.0
                continue
            for rt in role_tags:
                if rt in tt or tt in rt:
                    score += 0.5
                    break
        if score > best_score:
            best_score = score
            best_match = role_id

    return best_match


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
        logger.warning(
            "No solver for ticket #%d tags=%s, escalating to CEO",
            ticket.id,
            ticket.tags,
        )
        await _escalate_to_ceo(ticket, session)
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
            ticket_id=ticket.id,
        )


def _build_task_prompt(ticket: Ticket) -> str:
    """Build a task prompt for a persona based on the ticket."""
    return (
        f"You have been assigned ticket #{ticket.id}: {ticket.title}\n\n"
        f"Description: {ticket.description}\n"
        f"Priority: {ticket.priority}\n"
        f"Tags: {', '.join(ticket.tags)}\n"
        f"Context: {ticket.context}\n\n"
        f"INSTRUCTIONS:\n"
        f"1. Do the work described in this ticket.\n"
        f"2. ALWAYS use write_file to save your output (code, documents, etc.) "
        f"to the workspace. Do NOT just return code as text.\n"
        f"3. When done, call update_ticket with ticket_id={ticket.id}, "
        f"a brief result summary, and status='review'.\n"
        f"4. Keep deliverables focused: runnable code files, HTML pages, "
        f"or markdown docs. No cloud infra or deployment configs."
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

        reviewer = await session.get(Persona, ticket.created_by)
        if not reviewer:
            logger.info(
                "Creator %s not found, falling back to manager",
                ticket.created_by,
            )
            q = select(Persona).where(Persona.type == "manager", Persona.status == "active")
            result = await session.execute(q)
            reviewer = result.scalars().first()

    if reviewer:
        logger.info(
            "Reviewer for ticket #%d: %s (%s)",
            ticket_id,
            reviewer.name,
            reviewer.id,
        )
        task = (
            f"Review ticket #{ticket.id}: {ticket.title}\n\n"
            f"Solution: {ticket.result}\n\n"
            "If the solution is good, call update_ticket with status='done'.\n"
            "If not, call update_ticket with status='rejected' and explain."
        )
        _spawn_persona_task(reviewer, task, f"review-ticket-{ticket.id}")


def _spawn_persona_task(persona: Persona, task: str, label: str, ticket_id: int | None = None):
    """Fire-and-forget an async persona run with state tracking."""

    async def _run():
        try:
            await set_persona_state(persona.id, "working")
            if ticket_id:
                await _set_ticket_in_progress(ticket_id, persona.id)
            result = await run_persona(persona, task)

            # Store token usage on ticket
            if ticket_id and (result.input_tokens or result.output_tokens):
                await _add_ticket_tokens(ticket_id, result.input_tokens, result.output_tokens)
        except Exception:
            logger.exception("Background persona task %s failed", label)
            await set_persona_state(persona.id, "blocked")
        else:
            await set_persona_state(persona.id, "idle")
            # Greedy: solver looks for next unassigned ticket
            if persona.type == "solver":
                await _greedy_pickup(persona)

    t = asyncio.create_task(_run(), name=label)
    _running_tasks.add(t)
    t.add_done_callback(_running_tasks.discard)
    logger.info("Spawned background task: %s", label)


async def _set_ticket_in_progress(ticket_id: int, persona_id: str) -> None:
    """Mark a ticket as in_progress when a solver starts working on it."""
    async with async_session() as session:
        ticket = await session.get(Ticket, ticket_id)
        if ticket and ticket.status in ("assigned", "open"):
            ticket.status = "in_progress"
            log = WorkLog(
                persona_id=persona_id,
                action="started",
                ticket_id=ticket_id,
            )
            session.add(log)
            await session.commit()
            logger.info(
                "Ticket #%d now in_progress (solver %s started)",
                ticket_id,
                persona_id,
            )


async def _add_ticket_tokens(ticket_id: int, tokens_in: int, tokens_out: int) -> None:
    """Accumulate token usage on a ticket."""
    async with async_session() as session:
        ticket = await session.get(Ticket, ticket_id)
        if ticket:
            ticket.tokens_in = (ticket.tokens_in or 0) + tokens_in
            ticket.tokens_out = (ticket.tokens_out or 0) + tokens_out
            await session.commit()


async def _greedy_pickup(persona: Persona) -> None:
    """After finishing a task, solver looks for the next unassigned ticket."""
    try:
        load_company_config()
    except FileNotFoundError:
        return

    async with async_session() as session:
        result = await session.execute(
            select(Ticket).where(
                Ticket.status == "open",
                Ticket.assigned_to.is_(None),
            )
        )
        orphans = result.scalars().all()

    if not orphans:
        return

    # Find best match for this solver's skills
    picks_up = persona.picks_up or persona.skills or []
    best_ticket = None
    best_score = 0.0
    for ticket in orphans:
        from opencompany.company.taskboard import _fuzzy_tag_score

        score = _fuzzy_tag_score({s.lower() for s in picks_up}, {t.lower() for t in ticket.tags})
        if score > best_score:
            best_score = score
            best_ticket = ticket

    if not best_ticket:
        return

    logger.info(
        "Greedy pickup: %s grabs ticket #%d (score=%.1f)",
        persona.id,
        best_ticket.id,
        best_score,
    )
    # Route through normal flow so all logging/state tracking happens
    await _route_ticket(best_ticket.id)


async def _escalate_to_ceo(ticket: Ticket, session) -> None:
    """Assign an unmatched ticket to the CEO for re-tagging or role creation."""
    ceo = await session.get(Persona, "ceo")
    if not ceo or ceo.status != "active":
        logger.warning("CEO not available, ticket #%d stays unassigned", ticket.id)
        return

    ticket.assigned_to = "ceo"
    ticket.status = "assigned"
    log = WorkLog(persona_id="ceo", action="escalated", ticket_id=ticket.id)
    session.add(log)
    await session.commit()
    logger.info("Escalated ticket #%d to CEO (no matching solver)", ticket.id)

    _spawn_persona_task(
        ceo,
        f"Ticket #{ticket.id} ({ticket.title}) could not be automatically assigned.\n"
        f"Tags: {', '.join(ticket.tags)}\n"
        f"Description: {ticket.description}\n\n"
        "No available persona matches these tags. You should either:\n"
        "1. Re-tag the ticket so it matches an existing team member\n"
        "2. Create a new role (create_role) and hire someone (via HR) to handle it\n"
        "3. Assign it to an existing team member via update_ticket",
        f"escalate-ticket-{ticket.id}",
    )


async def sweep_unassigned_tickets() -> int:
    """Find open unassigned tickets and try to route them.

    Called periodically by the scheduler and after new hires.
    Returns the number of tickets routed.
    """
    async with async_session() as session:
        result = await session.execute(
            select(Ticket).where(
                Ticket.status == "open",
                Ticket.assigned_to.is_(None),
            )
        )
        orphans = result.scalars().all()

    if not orphans:
        return 0

    logger.info("Sweep found %d unassigned tickets", len(orphans))
    routed = 0
    for ticket in orphans:
        try:
            await _route_ticket(ticket.id)
            routed += 1
        except Exception:
            logger.exception("Sweep failed for ticket #%d", ticket.id)

    return routed


async def start_event_listener():
    """Start listening for events from the bus."""
    logger.info("Company engine event listener started")
    await subscribe(handle_event)
