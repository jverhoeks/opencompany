# OpenCompany

Virtual AI company — autonomous agent personas coordinating via a task board.

## Stack

- **Python 3.14+**, managed with **uv**
- **FastAPI** + **Uvicorn** — REST gateway
- **SQLAlchemy 2 (async)** + **asyncpg** — Postgres models
- **Redis** — event bus (`opencompany.events.bus`)
- **APScheduler** — periodic scheduling
- **Strands Agents** + **LiteLLM** — agent runtime
- **python-telegram-bot** — Telegram channel adapter

## Project layout

```
src/opencompany/
  main.py            # entrypoint
  models/            # SQLAlchemy models (base, engine, db)
  company/           # personas, taskboard, scheduler, seed, engine
  agents/            # runner, prompts, tools/
  events/            # async event bus
  gateway/           # FastAPI API + channel adapters (telegram)
tests/               # pytest tests
config/company.yaml  # company definition (personas, departments)
```

## Commands

```bash
uv run opencompany          # start the server
uv run pytest               # run tests
uv run ruff check .         # lint
uv run ruff format .        # format
```

## Conventions

- Use **ruff** for linting and formatting (config in `pyproject.toml`).
- Pre-commit hook runs `ruff check` and `ruff format --check` on every commit.
- Keep imports sorted (ruff handles this via `isort` rules).
- Use `async`/`await` throughout — no blocking I/O in the event loop.
- Environment variables go in `.env` (never committed); see `.env.example`.
