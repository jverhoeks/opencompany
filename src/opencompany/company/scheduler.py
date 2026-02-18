"""Scheduler — periodic sweep for orphaned tickets.

Runs a sweep every 30 seconds to find open unassigned tickets
and try to route them. Tickets with no matching solver escalate to CEO.
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _sweep_job():
    """Periodic job to sweep unassigned tickets."""
    try:
        from opencompany.company.engine import sweep_unassigned_tickets

        count = await sweep_unassigned_tickets()
        if count:
            logger.info("Scheduled sweep routed %d tickets", count)
    except Exception:
        logger.exception("Sweep job failed")


def start_scheduler():
    scheduler.add_job(_sweep_job, "interval", seconds=30, id="sweep_unassigned")
    scheduler.start()
