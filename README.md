# OpenCompany

A virtual AI company where autonomous agent personas work like real employees.
Each persona has a distinct personality, trust level, and set of tools.
They coordinate through a shared task board, route work through an org hierarchy,
and can hire new team members when the company needs more capacity.

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

The system is built around a configurable org hierarchy defined in `config/company.yaml`.
Personas are assigned one of four types:

| Type | What they do | Triggered by |
|---|---|---|
| **Manager** | Delegates, prioritises, hires and fires personas | Chat, CEO kickoff, heartbeat |
| **Lead** | Routes work to solvers, reviews architecture | Tag-matched ticket routing |
| **Solver** | Picks up tickets matching their skills, does the work | `ticket.created` event |
| **Observer** | Watches sources on a schedule, creates tickets | Cron (APScheduler) |

### Org hierarchy & routing

Tickets flow through the hierarchy based on the active org style:

- **Hierarchical** (default): CEO → PM → Lead → Solver (tag-matched at each level)
- **Dictator**: CEO assigns everything directly
- **Holacracy**: Best-match solver picks up work directly

### Ticket lifecycle

```
open --> assigned --> in_progress --> review --> done
                                       |
                                       v
                                    rejected --> open (reassigned)
```

### Personality system

Each persona has a unique personality block with traits, communication style,
quirks, and catchphrases. These are injected into the system prompt so every
persona responds in character.

### Trust tiers

A four-level trust system controls tool access:

| Tier | Level | Access |
|---|---|---|
| **external** | 0 | Read-only (read_file, list_files, grep_code, list_tickets, web_search) |
| **solver** | 1 | + write_file, update_ticket, web_fetch, publish_file |
| **lead** | 2 | + create_ticket, send_message, contact_overseer |
| **full** | 3 | + hire_persona, fire_persona, create_role |

### Workspaces

Each persona gets a private workspace (`workspaces/private/{persona_id}/`).
A shared workspace (`workspaces/shared/`) lets personas publish files for
others to read via the `publish_file` tool.

### Durable memory

Personas retain knowledge across runs. The `remember` and `recall` tools
store facts, decisions, and context in the database. When memories exceed
a threshold, they are automatically compacted into summaries.

### Token budgets

Each persona has a configurable daily token budget. The system tracks usage
and blocks personas that exceed their limit, preventing runaway costs.

### Scheduler jobs

| Job | Interval | Purpose |
|---|---|---|
| **Sweep** | 30s | Routes open unassigned tickets |
| **CEO kickoff** | Configurable | CEO reviews board, creates strategic work |
| **Heartbeat** | Configurable | Idle personas autonomously check in and act |

## Quickstart

### Prerequisites

- Python 3.14+
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

Key environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | (required) | LiteLLM proxy API key |
| `OPENAI_API_BASE` | (required) | LiteLLM proxy URL |
| `DATABASE_URL` | (required) | Postgres connection string |
| `REDIS_URL` | (required) | Redis connection string |
| `API_KEY` | (empty = disabled) | Bearer token for API auth |
| `CEO_KICKOFF_INTERVAL_SECONDS` | 0 (disabled) | CEO auto-review interval |
| `HEARTBEAT_INTERVAL_SECONDS` | 0 (disabled) | Persona heartbeat interval |
| `TELEGRAM_BOT_TOKEN` | (optional) | Telegram bot integration |

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

All endpoints require Bearer token authentication when `API_KEY` is set.

```bash
# Add to all requests when auth is enabled:
-H "Authorization: Bearer <your-api-key>"
```

### Personas

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/personas` | List active personas (paginated) |
| `GET` | `/api/personas/{id}` | Get persona details |

### Tickets

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/tickets?status=open` | List tickets by status |
| `POST` | `/api/tickets` | Create a ticket |
| `PATCH` | `/api/tickets/{id}` | Update ticket (assign, change status) |

### Chat

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/chat` | Chat with a persona |

### Budget

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/budget` | List all persona budgets |
| `GET` | `/api/budget/{id}` | Get persona budget |
| `POST` | `/api/budget/{id}/reset` | Reset persona's daily usage |
| `POST` | `/api/budget/reset-all` | Reset all daily usage |

### Other

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check (db + redis) |
| `GET` | `/dashboard` | Web dashboard UI |

### Examples

```bash
# Create a ticket
curl -X POST http://localhost:8000/api/tickets \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"title": "Review auth module", "priority": "high", "tags": ["security"]}'

# Chat with a persona
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"persona_id": "ceo", "message": "What is the team working on?"}'
```

## Agent tools

18 tools available to personas (gated by trust tier):

| Tool | Trust tier | Purpose |
|---|---|---|
| `read_file` | external | Read files from workspace |
| `write_file` | solver | Write files to private workspace |
| `list_files` | external | List directory contents |
| `grep_code` | external | Search code with regex |
| `publish_file` | solver | Copy file from private to shared workspace |
| `create_ticket` | lead | Create task board items |
| `list_tickets` | external | Query task board |
| `update_ticket` | solver | Update ticket status/assignment |
| `hire_persona` | full | Hire a new persona |
| `fire_persona` | full | Remove a persona |
| `create_role` | full | Define a new role |
| `list_team` | external | View all personas |
| `send_message` | lead | Message another persona |
| `contact_overseer` | lead | Request guidance |
| `web_search` | external | Search the web |
| `web_fetch` | solver | Fetch and read web pages |
| `remember` | external | Store a memory |
| `recall` | external | Retrieve memories |

## Project structure

```
src/opencompany/
  main.py                     Entrypoint (FastAPI lifespan)
  models/
    db.py                     Persona, Ticket, PersonaMemory, WorkLog
    base.py                   SQLAlchemy DeclarativeBase
    engine.py                 Async session factory
  company/
    config.py                 Load & parse company.yaml
    engine.py                 Ticket routing, persona dispatch, event handling
    taskboard.py              Skill matching, ticket assignment
    personas.py               Hire / fire / list personas
    scheduler.py              Sweep, CEO kickoff, heartbeat jobs
    seed.py                   Seed personas from company.yaml
    budget.py                 Token budget tracking
    memory.py                 Durable persona memory (store/recall/compact)
    trust.py                  Trust tier tool filtering
    messaging.py              Inter-persona messaging
    overseer.py               Overseer guidance interface
  agents/
    runner.py                 Strands agent execution
    prompts.py                System prompt builder (+ personality injection)
    tools/                    @tool functions (18 tools)
  events/
    bus.py                    Redis pub/sub event bus
  gateway/
    api.py                    REST API endpoints (Bearer auth)
    dashboard.py              Web dashboard UI
    channels/telegram.py      Telegram bot adapter
config/company.yaml           Org chart, roles, personas, personalities
workspaces/                   Per-persona runtime sandboxes
```

## Development

```bash
uv run pytest                              # run tests (143 tests)
uv run pytest --cov=opencompany            # run with coverage (61%)
uv run ruff check .                        # lint
uv run ruff format .                       # format
```

Pre-commit hooks run `ruff check --fix` and `ruff format` on every commit.

## License

MIT
