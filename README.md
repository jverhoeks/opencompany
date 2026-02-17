# OpenCompany

A virtual AI company where autonomous agent personas work like real employees.
Observers scan your codebase on a schedule, create tickets for issues they find,
solvers pick up those tickets and do the work, and managers can hire new personas
on the fly when the team is overloaded.

```
          Telegram / API
               |
        +----- v ------+
        |   Gateway     |    FastAPI + channel adapters
        +------+--------+
               |
        +------v--------+
        | Company Engine |    event bus, scheduler, auto-assignment
        +--+----+----+--+
           |    |    |
           v    v    v
         PG  Redis  Workspaces
```

## How it works

The system is built around four persona types, defined in `config/company.yaml`:

| Type | What they do | Triggered by |
|---|---|---|
| **Observer** | Watches sources on a schedule, creates tickets | Cron (APScheduler) |
| **Solver** | Picks up tickets matching their skills, does the work | `ticket.created` event |
| **Reviewer** | Validates completed work, approves or rejects | `ticket.review` event |
| **Manager** | Delegates, prioritises, hires and fires personas | Chat, escalations |

### Ticket lifecycle

```
open --> assigned --> in_progress --> review --> done
                                       |
                                       v
                                    rejected --> open (reassigned)
```

When an observer creates a ticket, the engine publishes a `ticket.created` event
on Redis. The company engine matches the ticket's tags against solver skills,
picks the solver with the lowest workload, and dispatches the agent automatically.

### Example: security scan

1. APScheduler fires every 6 hours, triggering the **Security Analyst** (observer)
2. The analyst scans `/src/**` using `read_file` and `grep_code` tools
3. Finds a vulnerability and calls `create_ticket(priority="critical", tags=["security"])`
4. The **Security Engineer** (solver) auto-claims the ticket via skill matching
5. The engineer reads the ticket context, investigates, and writes a fix
6. Ticket moves to `review` -- the analyst reviews and approves

All actions are logged in the `work_log` table for performance tracking.

## Quickstart

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- Docker & Docker Compose (for Postgres and Redis)
- A LiteLLM-compatible API endpoint

### 1. Clone and install

```bash
git clone <repo-url> && cd opencompany
uv sync
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your LiteLLM proxy URL, API key, and optional Telegram bot token
```

### 3. Start infrastructure

```bash
docker compose up -d db redis
```

### 4. Run

```bash
uv run opencompany
```

The server starts on `http://localhost:8000`. On first boot it creates the
database tables and seeds personas from `config/company.yaml`.

### Docker (all-in-one)

```bash
docker compose up --build
```

## API

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/api/personas` | List active personas |
| `GET` | `/api/personas/{id}` | Get persona details |
| `GET` | `/api/tickets?status=open` | List tickets by status |
| `POST` | `/api/tickets` | Create a ticket |
| `POST` | `/api/chat` | Chat with a persona |

### Create a ticket

```bash
curl -X POST http://localhost:8000/api/tickets \
  -H "Content-Type: application/json" \
  -d '{"title": "Review auth module", "priority": "high", "tags": ["security"]}'
```

### Chat with a persona

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"persona_id": "ceo", "message": "What is the team working on?"}'
```

## Project structure

```
src/opencompany/
  main.py                     entrypoint (FastAPI lifespan)
  gateway/
    api.py                    REST endpoints
    channels/telegram.py      Telegram bot adapter
  company/
    engine.py                 event handling, auto-assignment, solver dispatch
    taskboard.py              ticket CRUD, skill matching
    personas.py               hire / fire / list personas
    scheduler.py              APScheduler observer triggers
    seed.py                   seed personas from company.yaml
  agents/
    runner.py                 Strands agent creation and execution
    prompts.py                system prompt builder
    tools/                    @tool functions (tickets, code, company)
  models/
    db.py                     SQLAlchemy models (Persona, Ticket, WorkLog, ...)
    base.py                   DeclarativeBase
    engine.py                 async session factory
  events/
    bus.py                    Redis pub/sub
config/company.yaml           initial org chart and persona definitions
workspaces/                   per-persona runtime sandboxes
```

## Configuration

Personas are defined in `config/company.yaml`. Each persona has an ID, name,
role, type, skill tags, tool access list, and a backstory that shapes their
behaviour. Observer personas additionally have `watches` entries that control
what they scan and how often.

Managers have access to `hire_persona` and `fire_persona` tools, so the company
can grow dynamically at runtime.

## Stack

| Component | Technology |
|---|---|
| API gateway | FastAPI + Uvicorn |
| Agent runtime | [Strands Agents](https://github.com/strands-agents/sdk-python) |
| LLM routing | LiteLLM (external proxy) |
| Database | PostgreSQL 17 + SQLAlchemy 2 (async) |
| Event bus | Redis 7 pub/sub |
| Scheduler | APScheduler |
| Chat | python-telegram-bot |
| Packaging | uv + hatchling |

## Development

```bash
uv run pytest               # run tests
uv run ruff check .         # lint
uv run ruff format .        # format
```

Pre-commit hooks run `ruff check --fix` and `ruff format` on every commit.
Install them with:

```bash
pre-commit install
```

## License

MIT
