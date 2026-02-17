# src/opencompany/main.py
import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI

import opencompany.models.db  # noqa: F401
from opencompany.agents.runner import register_tool
from opencompany.agents.tools import ALL_TOOLS
from opencompany.company.engine import start_event_listener
from opencompany.company.scheduler import register_observers, start_scheduler
from opencompany.company.seed import seed_company
from opencompany.gateway.api import router as api_router
from opencompany.gateway.channels.telegram import create_telegram_app
from opencompany.gateway.dashboard import router as dashboard_router
from opencompany.models.base import Base
from opencompany.models.engine import engine, set_main_loop

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _wait_for_db(retries: int = 20, delay: float = 1.0):
    """Wait until the database is reachable."""
    from sqlalchemy import text

    for attempt in range(1, retries + 1):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("Database is ready")
            return
        except Exception:
            if attempt == retries:
                raise
            logger.warning(f"DB not ready (attempt {attempt}/{retries}), retrying...")
            await asyncio.sleep(delay)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Store the main event loop for sync wrappers
    set_main_loop(asyncio.get_running_loop())

    # Register all tools
    for name, func in ALL_TOOLS.items():
        register_tool(name, func)
    logger.info(f"Registered {len(ALL_TOOLS)} tools")

    # Wait for DB
    await _wait_for_db()

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ready")

    # Seed personas
    await seed_company()

    # Start scheduler for observers
    await register_observers()
    start_scheduler()
    logger.info("Scheduler started")

    # Start event listener (runs in background)
    _listener_task = asyncio.create_task(start_event_listener())
    _listener_task.add_done_callback(
        lambda t: logger.error("Event listener died: %s", t.exception()) if t.exception() else None
    )
    logger.info("Event listener started")

    # Start Telegram bot
    telegram_app = create_telegram_app()
    if telegram_app:
        await telegram_app.initialize()
        await telegram_app.start()
        await telegram_app.updater.start_polling()
        logger.info("Telegram bot started")

    yield

    # Shutdown
    if telegram_app:
        await telegram_app.updater.stop()
        await telegram_app.stop()
        await telegram_app.shutdown()

    await engine.dispose()


app = FastAPI(title="OpenCompany", version="0.1.0", lifespan=lifespan)
app.include_router(api_router, prefix="/api")
app.include_router(dashboard_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


def main():
    uvicorn.run("opencompany.main:app", host="0.0.0.0", port=8000, reload=True)
