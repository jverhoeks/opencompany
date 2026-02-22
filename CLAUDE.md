# OpenCompany

Virtual AI company — autonomous agent personas coordinating via a task board.

## Stack

- **Python 3.14+**, managed with **uv**
- **FastAPI** + **Uvicorn** — REST gateway (Bearer token auth)
- **SQLAlchemy 2 (async)** + **asyncpg** — Postgres models
- **Redis** — event bus (`opencompany.events.bus`)
- **APScheduler** — periodic scheduling (sweep, CEO kickoff, heartbeat)
- **Strands Agents** + **LiteLLM** — agent runtime
- **python-telegram-bot** — Telegram channel adapter

## Project layout

```
src/opencompany/
  main.py            # entrypoint
  models/            # SQLAlchemy models (Persona, Ticket, PersonaMemory, WorkLog)
  company/           # engine, config, scheduler, personas, taskboard, budget, memory, trust
  agents/            # runner, prompts, tools/ (18 tools gated by trust tiers)
  events/            # Redis pub/sub event bus
  gateway/           # FastAPI API + dashboard + Telegram adapter
tests/               # pytest tests (143 tests, 61% coverage)
config/company.yaml  # org chart, roles, personas, personalities
```

## Commands

```bash
uv run opencompany              # start the server
uv run pytest                   # run tests
uv run pytest --cov=opencompany # run with coverage
uv run ruff check .             # lint
uv run ruff format .            # format
```

## Key subsystems

- **Trust tiers**: external < solver < lead < full — controls tool access per persona type
- **Personality**: each persona has traits, communication style, quirks, catchphrases in prompts
- **Workspaces**: private per-persona + shared workspace with `publish_file`
- **Memory**: durable store/recall/compact across agent runs (PersonaMemory table)
- **Budget**: per-persona daily token limits tracked in DB
- **Heartbeat**: idle personas autonomously check in on configurable interval
- **Routing**: hierarchical (CEO→PM→Lead→Solver), dictator, or holacracy org styles

## Conventions

- Use **ruff** for linting and formatting (config in `pyproject.toml`).
- Pre-commit hook runs `ruff check` and `ruff format --check` on every commit.
- Keep imports sorted (ruff handles this via `isort` rules).
- Use `async`/`await` throughout — no blocking I/O in the event loop.
- Environment variables go in `.env` (never committed); see `.env.example`.
- Tests use in-memory SQLite via `db_engine` fixture in `conftest.py`.
- Mock `run_persona` with `AsyncMock` and patch `async_session` with test factory for e2e tests.
