"""Minimal scheduler — observer cron logic has been removed.

Leads are now active participants routed via the engine,
not passive watchers on cron schedules.
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def start_scheduler():
    scheduler.start()
