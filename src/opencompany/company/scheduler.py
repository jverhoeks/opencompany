"""Scheduler — periodic sweep for orphaned tickets + CEO auto-kickoff.

Runs a sweep every 30 seconds to find open unassigned tickets
and try to route them. Tickets with no matching solver escalate to CEO.

Optionally runs a CEO kickoff job that triggers the CEO to review
the board and create work. Disabled by default (CEO_KICKOFF_INTERVAL_SECONDS=0).
"""

import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

CEO_KICKOFF_PROMPT = (
    "Review the task board. Look at open tickets, team capacity, and company goals.\n"
    "Based on what you see, take action:\n"
    "- Create new strategic tickets if the board is empty or needs direction\n"
    "- Re-prioritize or re-tag tickets that are stuck\n"
    "- Create HR tickets to hire if you see skill gaps\n"
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


def start_scheduler():
    scheduler.add_job(_sweep_job, "interval", seconds=30, id="sweep_unassigned")

    ceo_interval = int(os.environ.get("CEO_KICKOFF_INTERVAL_SECONDS", "0"))
    if ceo_interval > 0:
        scheduler.add_job(
            _ceo_kickoff_job,
            "interval",
            seconds=ceo_interval,
            id="ceo_kickoff",
        )
        logger.info("CEO kickoff enabled: every %d seconds", ceo_interval)

    scheduler.start()
