# src/opencompany/main.py
import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import opencompany.models.db  # noqa: F401
from opencompany.agents.runner import register_tool
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

_log_level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
_log_format = "%(asctime)s %(levelname)-8s %(name)s  %(message)s"

logging.basicConfig(level=_log_level, format=_log_format)

# Also log to file if LOG_DIR is set (mapped volume in Docker)
_log_dir = os.environ.get("LOG_DIR", "")
if _log_dir:
    os.makedirs(_log_dir, exist_ok=True)
    _fh = logging.FileHandler(os.path.join(_log_dir, "opencompany.log"))
    _fh.setLevel(_log_level)
    _fh.setFormatter(logging.Formatter(_log_format))
    logging.getLogger().addHandler(_fh)

logger = logging.getLogger(__name__)


async def _run_migrations():
    """Run Alembic migrations via subprocess to avoid event-loop conflicts."""
    import subprocess

    result = await asyncio.to_thread(
        subprocess.run,
        ["alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        logger.error("Alembic migration failed:\n%s", result.stderr)
        raise RuntimeError(f"Migration failed: {result.stderr}")
    if result.stdout:
        for line in result.stdout.strip().splitlines():
            logger.info("alembic: %s", line)


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


async def _ceo_greet_overseer():
    """On startup, CEO sends a welcome message to the overseer (customer)."""
    try:
        from opencompany.company.budget import check_budget
        from opencompany.company.engine import _spawn_persona_task
        from opencompany.models.db import Persona
        from opencompany.models.engine import async_session

        async with async_session() as session:
            ceo = await session.get(Persona, "ceo")
            if not ceo or ceo.status != "active":
                logger.info("CEO greeting skipped: CEO not active")
                return

        has_budget, _ = await check_budget("ceo")
        if not has_budget:
            logger.info("CEO greeting skipped: CEO over budget")
            return

        _spawn_persona_task(
            ceo,
            "The company just started up. Greet the customer (overseer) via "
            "contact_overseer with a warm, professional welcome. Introduce "
            "yourself briefly and let them know you and the team are ready to "
            "help. Ask what they'd like the company to work on today. "
            "Keep it friendly and concise — one short paragraph.",
            "ceo-greeting",
        )
        logger.info("CEO greeting task spawned")
    except Exception:
        logger.exception("CEO greeting failed (non-fatal)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Store the main event loop for sync-to-async bridging in tool threads
    set_main_loop(asyncio.get_running_loop())

    # Register all tools
    from opencompany.agents.tools import ALL_TOOLS

    for name, func in ALL_TOOLS.items():
        register_tool(name, func)
    logger.info(f"Registered {len(ALL_TOOLS)} tools")

    # Wait for DB
    await _wait_for_db()
    # Dispose pool before Alembic to avoid advisory lock contention
    await engine.dispose()

    # Run Alembic migrations
    await _run_migrations()
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

    # CEO welcome: greet the overseer on startup
    await _ceo_greet_overseer()

    # Start Telegram bot (non-fatal — app works without it)
    telegram_app = create_telegram_app()
    if telegram_app:
        try:
            await telegram_app.initialize()
            await telegram_app.start()
            await telegram_app.updater.start_polling()
            logger.info("Telegram bot started")
        except Exception:
            logger.warning("Telegram bot failed to start (non-fatal)", exc_info=True)
            telegram_app = None

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
    cors_origins = ["http://localhost:8000", "http://127.0.0.1:8000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")
app.include_router(dashboard_router)

_static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


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
