import asyncio
import os
import socket
import threading
from datetime import datetime
from pathlib import Path

import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# ---------------------------------------------------------------------------
# Make PostgreSQL JSONB compile as plain JSON on SQLite so we can run
# the full schema in-memory without Docker.
# ---------------------------------------------------------------------------
from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

import opencompany.models.db  # noqa: F401 — register models with Base
from opencompany.gateway.api import router as api_router
from opencompany.gateway.dashboard import router as dashboard_router
from opencompany.models.base import Base
from opencompany.models.db import Persona, Ticket


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(autouse=True)
def _reset_asyncio_thread_state():
    """Clear stale thread-local running-loop state between tests.

    pytest-playwright's synchronous sessions and pytest-asyncio's event
    loops can leave ``asyncio._get_running_loop`` pointing at a closed
    loop on this thread. That stale reference later breaks
    ``loop.run_until_complete`` in sync tests (``_run_async`` fallback)
    and async fixtures (``RuntimeError: Cannot run the event loop while
    another loop is running``). Reset before and after each test.
    """
    import asyncio.events

    asyncio.events._set_running_loop(None)
    yield
    asyncio.events._set_running_loop(None)


@pytest.fixture
async def db_engine():
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------
def mock_run_async(result=None, *, raises: BaseException | None = None):
    """Build a ``side_effect`` for any coroutine-consuming sync seam.

    Use when patching functions that accept a coroutine but you don't want
    to actually run it — e.g. ``opencompany.utils._run_async`` or
    ``asyncio.create_task``. A plain ``return_value=X`` leaves the coroutine
    argument orphaned, producing ``RuntimeWarning: coroutine '...' was never
    awaited`` (often attributed to unrelated tests by Python's GC).

    Example::

        with patch("opencompany.utils._run_async", side_effect=mock_run_async(7)):
            ...
        with patch(
            "opencompany.main.asyncio.create_task",
            side_effect=mock_run_async(cancelled_future),
        ):
            ...

    The returned callable closes the supplied coroutine (when present) then
    returns ``result`` — or raises ``raises`` if provided.
    """

    def _impl(coro=None):
        close = getattr(coro, "close", None)
        if callable(close):
            close()
        if raises is not None:
            raise raises
        return result

    return _impl


# ---------------------------------------------------------------------------
# Markdown test report (tests.md)
# ---------------------------------------------------------------------------
def pytest_terminal_summary(terminalreporter, config):
    """Generate tests.md after the test run with results and coverage."""
    stats = terminalreporter.stats
    passed = len(stats.get("passed", []))
    failed = len(stats.get("failed", []))
    errors = len(stats.get("error", []))
    skipped = len(stats.get("skipped", []))
    total = passed + failed + errors + skipped
    duration = getattr(terminalreporter, "_sessionstarttime", None)
    if duration is not None:
        import time

        duration = time.time() - duration

    # Group results by test file
    results_by_file: dict[str, list[tuple[str, str]]] = {}
    for status_key, symbol in [
        ("passed", "pass"),
        ("failed", "FAIL"),
        ("error", "ERROR"),
        ("skipped", "skip"),
    ]:
        for report in stats.get(status_key, []):
            fspath = report.fspath
            nodeid = report.nodeid
            test_name = nodeid.split("::")[-1] if "::" in nodeid else nodeid
            results_by_file.setdefault(fspath, []).append((test_name, symbol))

    # Collect coverage data if available
    cov_plugin = config.pluginmanager.getplugin("_cov")
    cov_lines = []
    total_stmts = total_miss = 0
    if cov_plugin and hasattr(cov_plugin, "cov_controller"):
        cov = getattr(cov_plugin.cov_controller, "cov", None)
        if cov:
            analysis_data = []
            for filename in sorted(cov.get_data().measured_files()):
                try:
                    analysis = cov.analysis2(filename)
                    stmts = len(analysis[1])
                    miss = len(analysis[3])
                    cover = int((stmts - miss) / stmts * 100) if stmts else 100
                    short = filename
                    for marker in ("/src/opencompany/", "\\src\\opencompany\\"):
                        idx = filename.find(marker)
                        if idx >= 0:
                            short = "opencompany/" + filename[idx + len(marker) :]
                            break
                    total_stmts += stmts
                    total_miss += miss
                    analysis_data.append((short, stmts, miss, cover))
                except Exception:
                    continue
            cov_lines = analysis_data

    total_cover = int((total_stmts - total_miss) / total_stmts * 100) if total_stmts else 0

    # Build markdown
    lines = [
        "# Test Report",
        "",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"**Duration:** {duration:.1f}s" if duration else "",
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "|--------|-------|",
        f"| Total  | {total} |",
        f"| Passed | {passed} |",
        f"| Failed | {failed} |",
        f"| Errors | {errors} |",
        f"| Skipped | {skipped} |",
        f"| **Coverage** | **{total_cover}%** |",
        "",
    ]

    # Test results by file
    lines.append("## Test Results")
    lines.append("")
    for fspath in sorted(results_by_file):
        fname = os.path.basename(fspath)
        tests = results_by_file[fspath]
        pass_count = sum(1 for _, s in tests if s == "pass")
        fail_count = sum(1 for _, s in tests if s in ("FAIL", "ERROR"))
        status_icon = "FAIL" if fail_count else "ok"
        lines.append(f"### {fname} ({pass_count}/{len(tests)} passed) {status_icon}")
        lines.append("")
        lines.append("| Test | Status |")
        lines.append("|------|--------|")
        for test_name, symbol in tests:
            lines.append(f"| `{test_name}` | {symbol} |")
        lines.append("")

    # Coverage table
    if cov_lines:
        lines.append("## Coverage")
        lines.append("")
        lines.append("| Module | Stmts | Miss | Cover |")
        lines.append("|--------|-------|------|-------|")
        for short, stmts, miss, cover in cov_lines:
            bar = "!" if cover < 50 else ""
            lines.append(f"| `{short}` | {stmts} | {miss} | {cover}%{bar} |")
        lines.append(f"| **TOTAL** | **{total_stmts}** | **{total_miss}** | **{total_cover}%** |")
        lines.append("")

    # Write to project root
    root = str(config.rootdir)
    report_path = os.path.join(root, "tests.md")
    with open(report_path, "w") as f:
        f.write("\n".join(lines))
    terminalreporter.write_line(f"\nMarkdown report written to {report_path}")


# ---------------------------------------------------------------------------
# Live server fixture for Playwright E2E tests
# ---------------------------------------------------------------------------
def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _seed_and_build_app():
    """Create an in-memory DB, seed it, and return (app, engine)."""
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        session.add(Persona(id="ceo", name="Alice CEO", role="ceo", type="manager"))
        session.add(Persona(id="hr", name="Bob HR", role="hr", type="manager", reports_to="ceo"))
        session.add(Persona(id="pm", name="Carol PM", role="pm", type="manager", reports_to="ceo"))
        session.add(
            Persona(
                id="tech-lead",
                name="Dave TL",
                role="tech-lead",
                type="lead",
                reports_to="pm",
            )
        )
        session.add(
            Persona(
                id="dev1",
                name="Eve Dev",
                role="backend-dev",
                type="solver",
                reports_to="tech-lead",
            )
        )
        session.add(
            Persona(
                id="dev2",
                name="Frank Dev",
                role="frontend-dev",
                type="solver",
                reports_to="tech-lead",
            )
        )
        session.add(
            Persona(
                id="fired1",
                name="Ghost",
                role="backend-dev",
                type="solver",
                status="fired",
                reports_to="tech-lead",
            )
        )
        session.add(
            Ticket(
                title="Setup CI",
                status="open",
                created_by="ceo",
                tags=["backend"],
                priority="high",
            )
        )
        session.add(
            Ticket(
                title="Build API",
                status="assigned",
                assigned_to="dev1",
                created_by="pm",
                tags=["backend"],
            )
        )
        session.add(
            Ticket(
                title="Fix bug",
                status="in_progress",
                assigned_to="dev2",
                created_by="tech-lead",
                tags=["frontend"],
                priority="high",
            )
        )
        session.add(
            Ticket(
                title="Code review",
                status="review",
                assigned_to="dev1",
                created_by="pm",
            )
        )
        session.add(
            Ticket(
                title="Deploy v1",
                status="done",
                assigned_to="dev1",
                created_by="ceo",
            )
        )
        await session.commit()

    test_app = FastAPI()

    async def _get_test_session():
        async with factory() as session:
            yield session

    from opencompany.models.engine import get_session

    test_app.dependency_overrides[get_session] = _get_test_session
    test_app.include_router(api_router, prefix="/api")
    test_app.include_router(dashboard_router)

    static_dir = Path(__file__).resolve().parent.parent / "src" / "opencompany" / "static"
    test_app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    return test_app, engine


def _run_in_thread(coro):
    """Run a coroutine in a new thread with its own event loop, return the result."""
    result = None
    exc = None

    def _target():
        nonlocal result, exc
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(coro)
        except Exception as e:
            exc = e
        finally:
            loop.close()

    t = threading.Thread(target=_target)
    t.start()
    t.join()
    if exc:
        raise exc
    return result


@pytest.fixture
def live_server():
    """Start a real HTTP server with seeded data for Playwright tests."""
    import time

    import httpx

    test_app, engine = _run_in_thread(_seed_and_build_app())

    port = _free_port()
    cfg = uvicorn.Config(test_app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(cfg)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Poll until the server is ready
    for _ in range(50):
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/dashboard")
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(0.1)

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=5)
    _run_in_thread(engine.dispose())
