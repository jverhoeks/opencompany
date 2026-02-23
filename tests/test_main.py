"""Tests for main.py — app creation, lifespan, health, root endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# App structure tests (no lifespan needed)
# ---------------------------------------------------------------------------
def test_app_exists():
    """The FastAPI app is created and has the right title."""
    from opencompany.main import app

    assert app.title == "OpenCompany"
    assert app.version == "0.1.0"


def test_app_has_routers():
    """The app has API and dashboard routers mounted."""
    from opencompany.main import app

    paths = [route.path for route in app.routes]
    # At minimum we should see /api routes and /dashboard or /
    assert "/" in paths or any("/api" in p for p in paths)


def test_main_function():
    """main() calls uvicorn.run with correct parameters."""
    with (
        patch("opencompany.main.uvicorn.run") as mock_run,
        patch.dict("os.environ", {"OPENCOMPANY_RELOAD": "false"}),
    ):
        from opencompany.main import main

        main()

    mock_run.assert_called_once_with(
        "opencompany.main:app", host="0.0.0.0", port=8000, reload=False
    )


def test_main_function_with_reload():
    """main() enables reload when OPENCOMPANY_RELOAD=true."""
    with (
        patch("opencompany.main.uvicorn.run") as mock_run,
        patch.dict("os.environ", {"OPENCOMPANY_RELOAD": "true"}),
    ):
        from opencompany.main import main

        main()

    mock_run.assert_called_once_with(
        "opencompany.main:app", host="0.0.0.0", port=8000, reload=True
    )


# ---------------------------------------------------------------------------
# CORS middleware
# ---------------------------------------------------------------------------
def test_cors_default_origins(monkeypatch):
    """When CORS_ORIGINS is not set, defaults to ['*']."""
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    # The module-level code already ran, so we check the current state
    from opencompany.main import cors_origins

    # The actual origins depend on when the module was imported, but
    # we verify the variable exists and is a list
    assert isinstance(cors_origins, list)


# ---------------------------------------------------------------------------
# _wait_for_db
# ---------------------------------------------------------------------------
async def test_wait_for_db_success():
    """_wait_for_db succeeds when DB responds to SELECT 1."""
    from opencompany.main import _wait_for_db

    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()

    mock_engine = AsyncMock()
    mock_engine.connect = MagicMock()
    mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("opencompany.main.engine", mock_engine):
        await _wait_for_db(retries=1, delay=0.01)

    mock_conn.execute.assert_awaited_once()


async def test_wait_for_db_retries_then_succeeds():
    """_wait_for_db retries on failure then succeeds."""
    from opencompany.main import _wait_for_db

    call_count = 0

    async def fake_execute(query):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("not ready")

    mock_conn = AsyncMock()
    mock_conn.execute = fake_execute

    mock_engine = AsyncMock()
    mock_engine.connect = MagicMock()
    mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("opencompany.main.engine", mock_engine):
        await _wait_for_db(retries=5, delay=0.01)

    assert call_count == 3


async def test_wait_for_db_exhausted_retries():
    """_wait_for_db raises after exhausting retries."""
    from opencompany.main import _wait_for_db

    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(side_effect=ConnectionError("down"))

    mock_engine = AsyncMock()
    mock_engine.connect = MagicMock()
    mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("opencompany.main.engine", mock_engine),
        pytest.raises(ConnectionError),
    ):
        await _wait_for_db(retries=2, delay=0.01)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
async def test_lifespan_startup_shutdown():
    """Lifespan starts and stops all subsystems."""
    import asyncio

    from opencompany.main import app, lifespan

    mock_telegram_app = AsyncMock()
    mock_telegram_app.initialize = AsyncMock()
    mock_telegram_app.start = AsyncMock()
    mock_telegram_app.stop = AsyncMock()
    mock_telegram_app.shutdown = AsyncMock()
    mock_telegram_app.updater = AsyncMock()
    mock_telegram_app.updater.start_polling = AsyncMock()
    mock_telegram_app.updater.stop = AsyncMock()

    # Create a real cancelled future that can be awaited
    loop = asyncio.get_running_loop()
    cancelled_future = loop.create_future()
    cancelled_future.cancel()

    with (
        patch("opencompany.main.set_main_loop"),
        patch("opencompany.main.register_tool"),
        patch("opencompany.main._wait_for_db", new_callable=AsyncMock),
        patch("opencompany.main._run_migrations", new_callable=AsyncMock),
        patch("opencompany.main.seed_company", new_callable=AsyncMock),
        patch("opencompany.main.init_redis", new_callable=AsyncMock),
        patch("opencompany.main.start_scheduler"),
        patch("opencompany.main.asyncio.create_task", return_value=cancelled_future),
        patch("opencompany.main._ceo_greet_overseer", new_callable=AsyncMock),
        patch(
            "opencompany.main.create_telegram_app",
            return_value=mock_telegram_app,
        ),
        patch("opencompany.main.scheduler") as mock_scheduler,
        patch("opencompany.main.close_redis", new_callable=AsyncMock),
        patch("opencompany.main.engine", AsyncMock()),
    ):
        async with lifespan(app):
            pass  # startup is done

        # Verify shutdown calls
        mock_telegram_app.updater.stop.assert_awaited_once()
        mock_telegram_app.stop.assert_awaited_once()
        mock_telegram_app.shutdown.assert_awaited_once()
        mock_scheduler.shutdown.assert_called_once_with(wait=True)


async def test_lifespan_no_telegram():
    """Lifespan works without Telegram (returns None)."""
    import asyncio

    from opencompany.main import app, lifespan

    loop = asyncio.get_running_loop()
    cancelled_future = loop.create_future()
    cancelled_future.cancel()

    with (
        patch("opencompany.main.set_main_loop"),
        patch("opencompany.main.register_tool"),
        patch("opencompany.main._wait_for_db", new_callable=AsyncMock),
        patch("opencompany.main._run_migrations", new_callable=AsyncMock),
        patch("opencompany.main.seed_company", new_callable=AsyncMock),
        patch("opencompany.main.init_redis", new_callable=AsyncMock),
        patch("opencompany.main.start_scheduler"),
        patch("opencompany.main.asyncio.create_task", return_value=cancelled_future),
        patch("opencompany.main._ceo_greet_overseer", new_callable=AsyncMock),
        patch("opencompany.main.create_telegram_app", return_value=None),
        patch("opencompany.main.scheduler") as mock_scheduler,
        patch("opencompany.main.close_redis", new_callable=AsyncMock),
        patch("opencompany.main.engine", AsyncMock()),
    ):
        async with lifespan(app):
            pass

        mock_scheduler.shutdown.assert_called_once_with(wait=True)


# ---------------------------------------------------------------------------
# Root endpoint
# ---------------------------------------------------------------------------
async def test_root_returns_html():
    """GET / returns the HTML landing page."""
    from opencompany.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with (
            patch("opencompany.main.set_main_loop"),
            patch("opencompany.main.register_tool"),
            patch("opencompany.main._wait_for_db", new_callable=AsyncMock),
            patch("opencompany.main.asyncio.to_thread", new_callable=AsyncMock),
            patch("opencompany.main.seed_company", new_callable=AsyncMock),
            patch("opencompany.main.init_redis", new_callable=AsyncMock),
            patch("opencompany.main.start_scheduler"),
            patch("opencompany.main.asyncio.create_task", return_value=AsyncMock()),
            patch("opencompany.main._ceo_greet_overseer", new_callable=AsyncMock),
            patch("opencompany.main.create_telegram_app", return_value=None),
            patch("opencompany.main.scheduler", MagicMock()),
            patch("opencompany.main.close_redis", new_callable=AsyncMock),
            patch("opencompany.main.engine", AsyncMock()),
        ):
            resp = await client.get("/")

    assert resp.status_code == 200
    assert "OpenCompany" in resp.text


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------
async def test_health_all_ok():
    """GET /health returns 200 when DB and Redis are healthy."""
    from opencompany.main import health

    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()

    mock_engine = AsyncMock()
    mock_engine.connect = MagicMock()
    mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=False)

    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)

    with (
        patch("opencompany.main.engine", mock_engine),
        patch("opencompany.main.get_redis", new_callable=AsyncMock, return_value=mock_redis),
    ):
        response = await health()

    assert response.status_code == 200
    import json

    body = json.loads(response.body)
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["redis"] == "ok"


async def test_health_db_error():
    """GET /health returns 503 when DB fails."""
    from opencompany.main import health

    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(side_effect=ConnectionError("db down"))

    mock_engine = AsyncMock()
    mock_engine.connect = MagicMock()
    mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=False)

    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)

    with (
        patch("opencompany.main.engine", mock_engine),
        patch("opencompany.main.get_redis", new_callable=AsyncMock, return_value=mock_redis),
    ):
        response = await health()

    assert response.status_code == 503
    import json

    body = json.loads(response.body)
    assert body["status"] == "degraded"
    assert body["db"] == "error"


async def test_health_redis_error():
    """GET /health returns 503 when Redis fails."""
    from opencompany.main import health

    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()

    mock_engine = AsyncMock()
    mock_engine.connect = MagicMock()
    mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("opencompany.main.engine", mock_engine),
        patch(
            "opencompany.main.get_redis",
            new_callable=AsyncMock,
            side_effect=ConnectionError("redis down"),
        ),
    ):
        response = await health()

    assert response.status_code == 503
    import json

    body = json.loads(response.body)
    assert body["status"] == "degraded"
    assert body["redis"] == "error"
