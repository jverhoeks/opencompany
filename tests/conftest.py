import os
from datetime import datetime

import pytest

# ---------------------------------------------------------------------------
# Make PostgreSQL JSONB compile as plain JSON on SQLite so we can run
# the full schema in-memory without Docker.
# ---------------------------------------------------------------------------
from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

import opencompany.models.db  # noqa: F401 — register models with Base
from opencompany.models.base import Base


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


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
