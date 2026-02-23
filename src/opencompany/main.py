# src/opencompany/main.py
import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import opencompany.models.db  # noqa: F401
from opencompany.agents.runner import register_tool
from opencompany.agents.tools import ALL_TOOLS
from opencompany.company.engine import start_event_listener
from opencompany.company.scheduler import scheduler, start_scheduler
from opencompany.company.seed import seed_company
from opencompany.events.bus import close_redis, init_redis
from opencompany.gateway.api import router as api_router
from opencompany.gateway.channels.telegram import create_telegram_app
from opencompany.gateway.dashboard import router as dashboard_router
from opencompany.models.engine import engine
from opencompany.utils import set_main_loop

load_dotenv()

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
)
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
    # Store the main event loop for sync-to-async bridging in tool threads
    set_main_loop(asyncio.get_running_loop())

    # Register all tools
    for name, func in ALL_TOOLS.items():
        register_tool(name, func)
    logger.info(f"Registered {len(ALL_TOOLS)} tools")

    # Wait for DB
    await _wait_for_db()

    # Run Alembic migrations
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config("alembic.ini")
    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
    logger.info("Database migrations applied")

    # Seed personas
    await seed_company()

    # Initialise Redis connection pool
    await init_redis()
    logger.info("Redis connection pool ready")

    # Start scheduler (observer cron removed — leads are active participants now)
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

    # Graceful shutdown: scheduler, event listener, Redis
    scheduler.shutdown(wait=True)
    logger.info("Scheduler stopped")

    _listener_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await _listener_task
    logger.info("Event listener stopped")

    await close_redis()
    logger.info("Redis closed")

    await engine.dispose()


app = FastAPI(title="OpenCompany", version="0.1.0", lifespan=lifespan)

# CORS middleware
cors_origins_env = os.environ.get("CORS_ORIGINS", "")
if cors_origins_env:
    cors_origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]
else:
    cors_origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")
app.include_router(dashboard_router)


@app.get("/")
async def root():
    from fastapi.responses import HTMLResponse

    return HTMLResponse(
        """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>OpenCompany</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{min-height:100vh;display:flex;align-items:center;justify-content:center;
  background:#06080f;color:#d0d8e8;font-family:'Segoe UI',system-ui,sans-serif}
.card{text-align:center;padding:3rem;border:1px solid #1a2235;border-radius:12px;
  background:#0c1018;max-width:400px}
h1{font-size:1.6rem;margin-bottom:.5rem;color:#f0f4fa}
p{font-size:.95rem;color:#5a6a80;margin-bottom:1.5rem}
a{display:inline-block;padding:.7rem 2rem;background:#00e5ff;color:#06080f;
  text-decoration:none;border-radius:6px;font-weight:600;font-size:.95rem;
  transition:opacity .2s}
a:hover{opacity:.85}
.links{margin-top:1rem;font-size:.8rem;color:#5a6a80}
.links a{background:none;color:#5a6a80;padding:0;font-weight:400;text-decoration:underline}
</style></head><body>
<div class="card">
  <h1>OpenCompany</h1>
  <p>Virtual AI company &mdash; autonomous agent personas coordinating via a task board.</p>
  <a href="/dashboard">Open Dashboard</a>
  <div class="links"><a href="/health">Health</a> &middot; <a href="/docs">API Docs</a></div>
</div></body></html>"""
    )


@app.get("/health")
async def health():
    from fastapi.responses import JSONResponse
    from sqlalchemy import text

    from opencompany.events.bus import get_redis

    checks = {"db": "ok", "redis": "ok"}
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        checks["db"] = "error"
    try:
        r = await get_redis()
        await r.ping()
    except Exception:
        checks["redis"] = "error"
    status = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return JSONResponse({"status": status, **checks}, status_code=200 if status == "ok" else 503)


def main():
    reload = os.environ.get("OPENCOMPANY_RELOAD", "").lower() in ("1", "true")
    uvicorn.run("opencompany.main:app", host="0.0.0.0", port=8000, reload=reload)
