"""Scheduler — periodic sweep, CEO kickoff, persona heartbeat, and stale claim expiry.

Runs a sweep every 30 seconds to find open unassigned tickets
and try to route them. Tickets with no matching solver escalate to CEO.

Optionally runs a CEO kickoff job that triggers the CEO to review
the board and create work. Disabled by default (CEO_KICKOFF_INTERVAL_SECONDS=0).

Optionally runs a per-persona heartbeat that makes idle personas
check in autonomously. Disabled by default (HEARTBEAT_INTERVAL_SECONDS=0).

Runs a stale assignment expiry every 2 minutes to reclaim tickets stuck
in_progress for over 10 minutes (work-stealing from blocked personas).
"""

import logging
import os
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

CEO_KICKOFF_PROMPT = (
    "Review the task board. Look at open tickets, team capacity, and company goals.\n"
    "Based on what you see, take action:\n"
    "- Create new strategic tickets if the board is empty or needs direction\n"
    "- Re-prioritize or re-tag tickets that are stuck\n"
    "- Create HR tickets to hire ONLY if there is a genuine skill gap AND no one "
    "in that role already. Use list_team first to check existing headcount.\n"
    "- Follow up on in-progress work that seems stalled\n"
    "Be decisive and take concrete action."
)


async def _sweep_job():
    """Periodic job to sweep unassigned tickets."""
    try:
        from opencompany.company.engine import sweep_unassigned_tickets

        count = await sweep_unassigned_tickets()
        if count:
            logger.info("Scheduled sweep routed %d tickets", count)
    except Exception:
        logger.exception("Sweep job failed")


async def _ceo_kickoff_job():
    """Periodic job to trigger CEO to review the board and create work."""
    try:
        from opencompany.company.budget import check_budget
        from opencompany.company.engine import _spawn_persona_task, set_persona_state
        from opencompany.models.db import Persona
        from opencompany.models.engine import async_session

        async with async_session() as session:
            ceo = await session.get(Persona, "ceo")
            if not ceo or ceo.status != "active":
                logger.debug("CEO kickoff: CEO not active, skipping")
                return
            if ceo.activity_state != "idle":
                logger.debug("CEO kickoff: CEO is %s, skipping", ceo.activity_state)
                return

        has_budget, remaining = await check_budget("ceo")
        if not has_budget:
            logger.info("CEO kickoff: CEO over budget (remaining=%d), skipping", remaining)
            await set_persona_state("ceo", "blocked")
            return

        prompt = os.environ.get("CEO_KICKOFF_PROMPT", CEO_KICKOFF_PROMPT)
        logger.info("CEO kickoff: triggering CEO board review")
        _spawn_persona_task(ceo, prompt, "ceo-kickoff")
    except Exception:
        logger.exception("CEO kickoff job failed")


HEARTBEAT_PROMPTS = {
    "manager": (
        "Take a moment to review the state of the company.\n"
        "Check the task board for stuck tickets, unassigned work, or gaps.\n"
        "If you see something that needs action, take it."
    ),
    "lead": (
        "Review your department's tickets.\n"
        "Check if any are stuck, need re-assignment, or need new sub-tasks.\n"
        "Take action if needed."
    ),
    "solver": (
        "Check the task board for any unassigned tickets that match your skills.\n"
        "If you find one, pick it up."
    ),
}


async def _persona_heartbeat_job():
    """Periodic heartbeat: idle personas check in and take autonomous action."""
    try:
        from sqlalchemy import select

        from opencompany.company.budget import check_budget
        from opencompany.company.engine import _spawn_persona_task
        from opencompany.models.db import Persona
        from opencompany.models.engine import async_session

        async with async_session() as session:
            result = await session.execute(
                select(Persona).where(
                    Persona.status == "active",
                    Persona.activity_state == "idle",
                )
            )
            idle_personas = result.scalars().all()

        for persona in idle_personas:
            has_budget, _ = await check_budget(persona.id)
            if not has_budget:
                continue
            prompt = HEARTBEAT_PROMPTS.get(persona.type, HEARTBEAT_PROMPTS["solver"])
            _spawn_persona_task(persona, prompt, f"heartbeat-{persona.id}")
    except Exception:
        logger.exception("Persona heartbeat job failed")


_STALE_MINUTES = int(os.environ.get("STALE_ASSIGNMENT_MINUTES", "10"))


async def _expire_stale_assignments_job():
    """Reclaim tickets stuck in_progress for too long (work-stealing)."""
    try:
        from sqlalchemy import select

        from opencompany.events.bus import publish
        from opencompany.models.db import Ticket, WorkLog
        from opencompany.models.engine import async_session

        cutoff = datetime.now(UTC) - timedelta(minutes=_STALE_MINUTES)
        async with async_session() as session:
            result = await session.execute(
                select(Ticket).where(
                    Ticket.status == "in_progress",
                    Ticket.updated_at < cutoff,
                )
            )
            stale = result.scalars().all()
            if not stale:
                return

            count = 0
            for ticket in stale:
                old_assignee = ticket.assigned_to
                ticket.status = "open"
                ticket.assigned_to = None
                ticket.updated_at = datetime.now(UTC)
                log = WorkLog(
                    persona_id=old_assignee or "system",
                    action="expired",
                    ticket_id=ticket.id,
                    details=f"stale after {_STALE_MINUTES}m",
                )
                session.add(log)
                count += 1

            await session.commit()

            # Re-publish so the engine routes them
            for ticket in stale:
                await publish("ticket.created", {"ticket_id": ticket.id})

            logger.info(
                "Expired %d stale in_progress tickets (cutoff=%dm)",
                count,
                _STALE_MINUTES,
            )
    except Exception:
        logger.exception("Stale assignment expiry job failed")


def start_scheduler():
    scheduler.add_job(_sweep_job, "interval", seconds=30, id="sweep_unassigned")
    scheduler.add_job(
        _expire_stale_assignments_job,
        "interval",
        seconds=120,
        id="expire_stale_assignments",
    )

    ceo_interval = int(os.environ.get("CEO_KICKOFF_INTERVAL_SECONDS", "0"))
    if ceo_interval > 0:
        scheduler.add_job(
            _ceo_kickoff_job,
            "interval",
            seconds=ceo_interval,
            id="ceo_kickoff",
        )
        logger.info("CEO kickoff enabled: every %d seconds", ceo_interval)

    heartbeat_interval = int(os.environ.get("HEARTBEAT_INTERVAL_SECONDS", "0"))
    if heartbeat_interval > 0:
        scheduler.add_job(
            _persona_heartbeat_job,
            "interval",
            seconds=heartbeat_interval,
            id="persona_heartbeat",
        )
        logger.info("Persona heartbeat enabled: every %d seconds", heartbeat_interval)

    scheduler.start()
