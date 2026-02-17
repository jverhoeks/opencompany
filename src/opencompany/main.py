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
from opencompany.models.base import Base
from opencompany.models.engine import engine

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Register all tools
    for name, func in ALL_TOOLS.items():
        register_tool(name, func)
    logger.info(f"Registered {len(ALL_TOOLS)} tools")

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
    asyncio.create_task(start_event_listener())
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


@app.get("/health")
async def health():
    return {"status": "ok"}


def main():
    uvicorn.run("opencompany.main:app", host="0.0.0.0", port=8000, reload=True)
