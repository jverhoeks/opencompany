# OpenCompany — Codebase Analysis & Improvement Plan

**Date:** 2026-03-10
**Scope:** Architecture, Performance, Security, Usability, Usage

---

## Executive Summary

OpenCompany is a ~2,900 LOC Python platform that orchestrates autonomous AI agent personas through a shared task board. It features a clean layered architecture (gateway → company → agents → events → data), an expressive YAML-driven configuration system, and a real-time dashboard. The codebase is well-structured for its size with 351 tests at 61% coverage.

However, the analysis uncovered **critical security gaps** (committed credentials, unauthenticated dashboard, unenforced trust tiers), **performance bottlenecks** (thread pool saturation, missing DB indexes, uncapped concurrency), and **feature gaps** where subsystems are defined but not wired into the runtime (trust enforcement, auto-memory injection, Telegram bindings).

This document prioritizes findings into actionable work streams.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Critical Findings](#2-critical-findings)
3. [Security](#3-security)
4. [Performance](#4-performance)
5. [Usability & Developer Experience](#5-usability--developer-experience)
6. [Usage & Metrics](#6-usage--metrics)
7. [Improvement Plan](#7-improvement-plan)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  PRESENTATION LAYER                                          │
│  gateway/api.py (REST)  ·  dashboard.py (SSE+HTML)          │
│  channels/telegram.py                                        │
└───────────────────┬─────────────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────────┐
│  ORCHESTRATION LAYER (company/)                              │
│  engine · scheduler · personas · taskboard · budget          │
│  memory · policy · messaging · overseer · trust · config     │
└───────────────────┬─────────────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────────┐
│  AGENT LAYER (agents/)                                       │
│  runner  ·  prompts  ·  tools/ (24 tools)                    │
└───────────────────┬─────────────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────────┐
│  EVENT LAYER — events/bus.py (Redis Streams pub/sub)         │
└───────────────────┬─────────────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────────┐
│  DATA LAYER — models/db.py (SQLAlchemy 2 async + asyncpg)    │
└─────────────────────────────────────────────────────────────┘
```

### Strengths

- **Clean layered design** with clear package boundaries
- **Event-driven routing** via Redis Streams with at-least-once delivery
- **Elegant tool binding** — `_bind_persona_id` prevents agent identity hallucination
- **Flexible org styles** — hierarchical, dictator, holacracy switchable via one YAML line
- **Graceful degradation** — Telegram, Redis, heartbeat are all non-fatal optionals
- **MappedAsDataclass** gives type-safe model construction without separate DTOs
- **Smart test infra** — in-memory SQLite with JSONB→JSON compiler shim, auto markdown report

### Weaknesses

- **`company/engine.py` is a God class** (537 lines) handling routing, lifecycle, escalation, sweep, and prompt construction
- **Bidirectional dependency** between `company/` and `agents/` packages
- **Dual state** for personas (DB + YAML) with no reconciliation mechanism
- **Deferred imports** to mask circular dependencies (scheduler → engine)
- **Trust tiers defined but never enforced** at runtime
- **Memory subsystem built but not auto-injected** into prompts

---

## 2. Critical Findings

These cross-cutting issues emerged from multiple analysis perspectives and represent the highest-priority items.

### 2.1 Trust Tier Enforcement Is Dead Code

| Aspect | Detail |
|--------|--------|
| **What exists** | `trust.py` defines 4 tiers and `filter_tools_by_tier()` — fully implemented, fully tested |
| **What's missing** | `runner.py:create_agent()` resolves tools from `persona.tools` directly, never calls the filter |
| **Impact** | Any persona can use any tool listed in its YAML config regardless of trust level |
| **Fix complexity** | Low — one function call insertion in `create_agent()` |

### 2.2 Memory System Built But Not Wired

| Aspect | Detail |
|--------|--------|
| **What exists** | `memory.py:build_memory_context()`, `remember` and `recall` tools, `PersonaMemory` table |
| **What's missing** | `prompts.py:build_system_prompt()` never calls `build_memory_context()` |
| **Impact** | Agents have no persistent context across runs unless they explicitly call `recall` |
| **Fix complexity** | Low — add memory section to prompt builder |

### 2.3 Committed Credentials

| Aspect | Detail |
|--------|--------|
| **What exists** | `.env` file on disk with live `OPENAI_API_KEY` and `TELEGRAM_BOT_TOKEN` |
| **Impact** | Credential compromise if the repo is shared or the file was ever committed |
| **Fix** | Rotate immediately, audit git history, add `gitleaks` pre-commit hook |

### 2.4 Unauthenticated Dashboard

| Aspect | Detail |
|--------|--------|
| **What exists** | Full operational dashboard with workspace file access, overseer messages, live SSE |
| **What's missing** | No `Depends(verify_api_key)` on any dashboard route |
| **Impact** | Complete data exposure to any network-adjacent party |
| **Fix complexity** | Low — add auth dependency to the dashboard router |

---

## 3. Security

### Severity Matrix

| # | Finding | Severity | File | Effort |
|---|---------|----------|------|--------|
| S1 | Auth disabled when `API_KEY` unset (fails open) | Critical | `api.py:28` | S |
| S2 | Dashboard completely unauthenticated | Critical | `dashboard.py:136` | S |
| S3 | Trust tier filter never called at runtime | Critical | `runner.py:89` | S |
| S4 | `.env` contains live API keys | Critical | `.env` | S |
| S5 | `run_script` executes arbitrary code, inherits full env | Critical | `code.py:188` | L |
| S6 | SSRF via `web_fetch` — no internal network blocking | High | `web.py:10` | M |
| S7 | Ticket content injected unsanitized into agent prompts | High | `engine.py:235` | M |
| S8 | `send_message` allows persona impersonation | High | `messaging.py` | S |
| S9 | Dashboard workspace path traversal via symlinks | High | `dashboard.py:146` | S |
| S10 | Agents can modify `company.yaml` → inject malicious roles | High | `config.py:117` | M |
| S11 | CDN scripts without SRI; DOMPurify fallback serves raw HTML | High | `dashboard.html:9` | S |
| S12 | Hardcoded default DB credentials | High | `engine.py:5` | S |
| S13 | Redis deployed without authentication | High | `docker-compose.yml:19` | S |
| S14 | Timing attack on API key comparison | Medium | `api.py:32` | S |
| S15 | `PATCH /tickets` accepts arbitrary status values | Medium | `api.py:127` | S |
| S16 | CORS `allow_origins=["*"]` + `allow_credentials=True` | Medium | `main.py:193` | S |
| S17 | Policy docs injectable into all agent system prompts | Medium | `policy.py:108` | M |

**Effort key:** S = small (< 1 hour), M = medium (half day), L = large (multi-day)

---

## 4. Performance

### Severity Matrix

| # | Finding | Severity | File | Effort |
|---|---------|----------|------|--------|
| P1 | TOCTOU race in ticket assignment — no `SELECT FOR UPDATE` | High | `engine.py:61` | M |
| P2 | Executor threads blocked in `future.result(60)` — pool saturates silently | High | `runner.py:146` | M |
| P3 | No timeout on LLM execution — hung request holds thread forever | High | `runner.py:146` | S |
| P4 | Missing DB indexes in migrations (tickets.status, assigned_to, etc.) | High | migrations | M |
| P5 | Policy context queried from DB on every agent construction | Medium | `prompts.py:105` | S |
| P6 | Python-side JSONB tag filtering after full table load | Medium | `taskboard.py:119` | M |
| P7 | Dashboard SSE: 8 queries every 3 seconds per client | Medium | `dashboard.py:159` | M |
| P8 | Redis stream grows unboundedly — no `MAXLEN` | Medium | `bus.py:82` | S |
| P9 | `scheduler.shutdown(wait=True)` blocks the event loop | Medium | `main.py:176` | S |
| P10 | In-flight agent tasks not drained at shutdown | Medium | `main.py:169` | M |
| P11 | No retry logic for transient LLM errors (429, 503) | Medium | `runner.py:175` | M |
| P12 | Token budget checked only before run, not enforced mid-run | Medium | `engine.py:328` | L |
| P13 | Heartbeat can spawn duplicate tasks for same persona | Medium | `scheduler.py:104` | S |
| P14 | No backpressure on concurrent agent tasks | Medium | `engine.py:18` | M |
| P15 | No rate limiting on `POST /chat` or `POST /tickets` | Low | `api.py:168` | M |

---

## 5. Usability & Developer Experience

### What Works Well

- **README.md** is excellent — architecture diagram, full tool table, API reference, demo walkthrough
- **`uv run opencompany`** — single command to start, `uv run pytest` to test
- **Docker Compose** — production-realistic with health checks and named volumes
- **Dashboard** — real-time cyberpunk SPA with SSE, workspace browsing, overseer chat
- **Auto-migrations** — Alembic runs at startup, zero manual steps
- **Test infra** — in-memory SQLite, auto markdown report, `run_persona` mock boundary

### Key Pain Points

| # | Issue | Impact | Effort |
|---|-------|--------|--------|
| U1 | `.env.example` missing `SERPAPI_KEY`, `WORKSPACE_ROOT`, `AGENT_MAX_WORKERS`, `SCRIPT_TIMEOUT_SECONDS`, `CORS_ORIGINS` | Devs discover env vars by reading source | S |
| U2 | `company.yaml` is 1200 lines of demo artifacts, not a clean starter config | New users confused by 30+ personas | M |
| U3 | YAML references non-existent tools (`figma`, `slack`, `email`, `prometheus`) — silently ignored | Silent misconfiguration | S |
| U4 | Ticket status values are magic strings across 4+ files — no enum | Inconsistency, API only exposes 4 of 7 statuses | M |
| U5 | Agent task failures don't update ticket status — tickets stuck "in_progress" forever | Silent operational failure | M |
| U6 | No structured/JSON logging, no correlation IDs, no metrics endpoint | Debugging concurrent agents is guesswork | L |
| U7 | Dashboard title hardcoded to "NovaCraft — Control Tower" | Branded demo artifact | S |
| U8 | Telegram bindings config defined in YAML but code is a TODO stub | Config does nothing | M |
| U9 | `rebuild-all.sh` deletes everything without confirmation, no `set -e` | Data loss risk | S |
| U10 | No CLI subcommands (seed, reset, list-personas) — all via HTTP | Operational friction | M |
| U11 | Python version: README says 3.14+, pyproject.toml says >=3.13 | Minor confusion | S |
| U12 | No ARCHITECTURE.md, CONTRIBUTING.md, or CHANGELOG.md | Onboarding friction | M |

---

## 6. Usage & Metrics

### Codebase at a Glance

| Metric | Value |
|--------|-------|
| Source LOC | ~2,900 |
| Test LOC | ~2,000 |
| Python modules | 39 |
| Test files | 31 |
| Test functions | 351 |
| Coverage | 61% |
| Agent tools | 24 (docs say 18 — outdated) |
| DB tables | 6 |
| Event types | 2 (`ticket.created`, `ticket.review`) |
| REST endpoints | 20 |
| Dependencies (prod) | 14 packages |
| Org style configs | 3 (hierarchical, dictator, holacracy) |

### Dead Schema

These columns exist in the database but have no write paths:

| Column | Table | Notes |
|--------|-------|-------|
| `watches` | personas | Never set or queried |
| `reviewed_by` | tickets | Always NULL |
| `parent_id` | tickets | Sub-ticket FK, never used |
| `duration_sec` | work_log | Always NULL |
| `version` | policy_documents | Always 1, no increment logic |

### Unimplemented Features

| Feature | Status | What's Missing |
|---------|--------|----------------|
| Trust tier enforcement | Code exists, not wired | One call in `create_agent()` |
| Auto memory injection | Code exists, not wired | Call in `build_system_prompt()` |
| Telegram persona bindings | Config exists, code is TODO | `_resolve_persona()` implementation |
| `reject_policy` | Function exists | No agent tool wrapping it |
| Memory compaction scheduling | Function exists | No scheduler job |

---

## 7. Improvement Plan

### Phase 0 — Immediate Security (1-2 days)

> **Goal:** Eliminate critical vulnerabilities before any deployment.

| Task | Priority | Effort | Files |
|------|----------|--------|-------|
| Rotate OpenAI API key and Telegram bot token | P0 | 15min | External |
| Audit git history for `.env` commits | P0 | 15min | git |
| Add `gitleaks` or `detect-secrets` pre-commit hook | P0 | 30min | `.pre-commit-config.yaml` |
| Add auth to dashboard routes | P0 | 30min | `dashboard.py` |
| Make auth fail-closed when `API_KEY` unset | P0 | 30min | `api.py` |
| Wire `filter_tools_by_tier()` into `create_agent()` | P0 | 30min | `runner.py` |
| Add `run_script` to `TOOL_TIER_REQUIREMENTS`; default deny | P0 | 15min | `trust.py` |
| Fix timing attack: `hmac.compare_digest` for key comparison | P0 | 15min | `api.py` |
| Fix dashboard path traversal: `os.path.realpath` before prefix check | P0 | 15min | `dashboard.py` |
| Bind `from_persona_id` in `send_message` via `_bind_persona_id` | P0 | 30min | `messaging.py`, `runner.py` |
| Remove hardcoded DB credential fallback | P0 | 15min | `models/engine.py` |
| Block SSRF in `web_fetch` (RFC 1918, loopback, link-local) | P0 | 1h | `tools/web.py` |

### Phase 1 — Wire Up Existing Subsystems (3-5 days)

> **Goal:** Activate the trust, memory, and binding systems that are already built.

| Task | Priority | Effort | Files |
|------|----------|--------|-------|
| Inject `build_memory_context()` into `build_system_prompt()` | P1 | 1h | `prompts.py`, `memory.py` |
| Schedule periodic `compact_memories()` job | P1 | 1h | `scheduler.py`, `memory.py` |
| Implement Telegram persona binding resolution | P1 | 3h | `telegram.py`, `config.py` |
| Add `reject_policy` tool to `ALL_TOOLS` | P1 | 30min | `tools/policy.py`, `tools/__init__.py` |
| Create a `TicketStatus` enum, replace magic strings | P1 | 3h | `models/db.py`, `engine.py`, `taskboard.py`, `api.py` |
| Update agent task failure to set ticket status to "failed" | P1 | 1h | `engine.py` |
| Clean up dead schema columns (or add write paths) | P1 | 2h | `models/db.py`, migrations |
| Update CLAUDE.md: 24 tools, not 18 | P1 | 15min | `CLAUDE.md` |

### Phase 2 — Performance & Reliability (1-2 weeks)

> **Goal:** Make the system production-safe under concurrent load.

| Task | Priority | Effort | Files |
|------|----------|--------|-------|
| Add `SELECT FOR UPDATE` to ticket assignment | P2 | 2h | `engine.py`, `taskboard.py` |
| Create Alembic migration for missing indexes | P2 | 2h | `migrations/` |
| Add `asyncio.wait_for(timeout=300)` around LLM execution | P2 | 1h | `runner.py` |
| Add exponential backoff retry for transient LLM errors | P2 | 3h | `runner.py` |
| Add `MAXLEN` to Redis `XADD` calls | P2 | 30min | `bus.py` |
| Push JSONB tag filtering down to Postgres `@>` operator | P2 | 2h | `taskboard.py` |
| Cache `build_policy_context()` with TTL invalidation | P2 | 2h | `policy.py` |
| Add max concurrency cap for `_running_tasks` | P2 | 2h | `engine.py` |
| Fix heartbeat persona deduplication (check activity_state atomically) | P2 | 1h | `scheduler.py` |
| Refactor SSE to consume from Redis instead of polling DB | P2 | 4h | `dashboard.py` |
| Fix `scheduler.shutdown(wait=True)` blocking — use `await` | P2 | 30min | `main.py` |
| Drain in-flight tasks at shutdown | P2 | 2h | `main.py`, `engine.py` |
| Add rate limiting middleware (`slowapi` or custom) | P2 | 3h | `main.py`, `api.py` |

### Phase 3 — Usability & DX (1-2 weeks)

> **Goal:** Make the project welcoming for contributors and deployable without tribal knowledge.

| Task | Priority | Effort | Files |
|------|----------|--------|-------|
| Complete `.env.example` with all env vars | P3 | 30min | `.env.example` |
| Create a clean minimal `company.yaml` starter config | P3 | 2h | `config/` |
| Add YAML validation schema (Pydantic model for company config) | P3 | 4h | `config.py` |
| Warn on non-existent tool names in YAML during seed | P3 | 1h | `seed.py` |
| Add structured JSON logging mode | P3 | 3h | `main.py` |
| Add correlation ID to agent runs (persona_id + ticket_id) | P3 | 3h | `engine.py`, `runner.py` |
| Add SRI hashes to CDN scripts in dashboard | P3 | 30min | `dashboard.html` |
| Fix DOMPurify fallback to render plain text on load failure | P3 | 30min | `dashboard.html` |
| Add Redis authentication to docker-compose | P3 | 30min | `docker-compose.yml`, `bus.py` |
| Mount config volume read-only in Docker | P3 | 15min | `docker-compose.yml` |
| Add `set -e` and confirmation prompt to `rebuild-all.sh` | P3 | 15min | `rebuild-all.sh` |
| Fix Python version in README (>=3.13 per pyproject.toml) | P3 | 5min | `README.md` |
| Write ARCHITECTURE.md (end-to-end data flow documentation) | P3 | 4h | `ARCHITECTURE.md` |

### Phase 4 — Architecture Improvements (2-4 weeks)

> **Goal:** Address structural debt for long-term maintainability.

| Task | Priority | Effort | Files |
|------|----------|--------|-------|
| Decompose `engine.py` into `RoutingEngine`, `PersonaLifecycle`, `TicketOrchestrator` | P4 | 1w | `company/` |
| Break bidirectional dependency between `company/` and `agents/` | P4 | 3d | Multiple |
| Eliminate dual state (DB + YAML) for personas — use DB as source of truth | P4 | 3d | `personas.py`, `config.py`, `seed.py` |
| Add integration tests against real Postgres + Redis | P4 | 3d | `tests/` |
| Sandbox `run_script` in containers (gVisor/Docker-in-Docker) | P4 | 1w | `tools/code.py` |
| Add dead-letter handling for persistently failing events | P4 | 2d | `bus.py` |
| Add Prometheus `/metrics` endpoint | P4 | 2d | `main.py`, new `metrics.py` |
| Reach 80% test coverage | P4 | 1w | `tests/` |

---

## Risk/Impact Matrix

```
         High Impact
              │
    ┌─────────┼─────────┐
    │  S1-S5  │  P1-P3  │
    │ Phase 0 │ Phase 2 │   ← Do these first
    │(Security│(Perf    │
    │ critical│ critical│
    ├─────────┼─────────┤
    │  U1-U5  │  P4     │
    │ Phase 1 │ Phase 4 │   ← Do these next
    │(Wire up)│(Arch)   │
    │         │         │
    └─────────┼─────────┘
              │
         Low Impact
   Low Effort ────── High Effort
```

---

## Appendix: File Reference

| File | Lines | Role |
|------|-------|------|
| `main.py` | ~200 | Entrypoint, lifespan, startup sequence |
| `company/engine.py` | ~537 | Core orchestration (God class candidate) |
| `company/config.py` | ~160 | YAML config, mtime cache, runtime mutation |
| `agents/runner.py` | ~180 | Agent creation, tool binding, LLM execution |
| `agents/prompts.py` | ~100 | System prompt assembly |
| `agents/tools/__init__.py` | ~50 | Tool registry (24 tools) |
| `events/bus.py` | ~130 | Redis Streams pub/sub |
| `company/trust.py` | ~70 | Trust tiers (not enforced at runtime) |
| `company/taskboard.py` | ~170 | Ticket CRUD, fuzzy matching |
| `models/db.py` | ~140 | 6 ORM models |
| `models/engine.py` | ~15 | Async engine + session factory |
| `gateway/api.py` | ~190 | REST API endpoints |
| `gateway/dashboard.py` | ~210 | Dashboard + SSE + overseer + workspace |
| `gateway/channels/telegram.py` | ~80 | Telegram bot adapter |
| `company/scheduler.py` | ~150 | APScheduler jobs |
| `company/budget.py` | ~70 | Token budget management |
| `company/memory.py` | ~100 | Memory store/recall/compact |
| `company/policy.py` | ~150 | Policy CRUD + prompt context builder |
| `utils.py` | ~30 | `_run_async` sync-to-async bridge |
| `config/company.yaml` | ~1200 | Org chart, roles, personas |
| `tests/conftest.py` | ~160 | Test fixtures + markdown report hook |
