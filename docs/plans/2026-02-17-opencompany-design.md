# OpenCompany Design Document

**Date:** 2026-02-17
**Status:** Approved
**Author:** jjverhoeks + Claude

## Vision

A virtual AI company where autonomous agent personas work like real employees.
Observers scan code, docs, and infrastructure to create tickets. Solvers pick
up tickets by priority and execute. Reviewers validate work. Managers delegate
and hire new personas dynamically.

Built on Strands Agents SDK with LiteLLM proxy support, modeled after
OpenClaw's gateway architecture but focused entirely on the business
simulation layer.

---

## Architecture Overview

```
                  ┌─────────────────────────────────┐
  Telegram ──────>│                                 │
  Slack ─────────>│          GATEWAY                │
  Webhooks ──────>│   (FastAPI + WebSocket)          │
  Cron/Events ───>│                                 │
  Task Board UI ─>│                                 │
                  └──────────┬──────────────────────┘
                             │
                  ┌──────────v──────────────────────┐
                  │        COMPANY ENGINE            │
                  │                                  │
                  │  Persona Manager (org chart)     │
                  │  Task Board (ticket lifecycle)   │
                  │  Scheduler (observer triggers)   │
                  │  Event Bus (Redis pub/sub)       │
                  │  Agent Runner (Strands + LiteLLM)│
                  └──────────┬──────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              v              v              v
        PostgreSQL        Redis        Workspaces
        (personas,      (events,      (per-persona
         tickets,        queue,        files, logs,
         memory,         locks)        sessions)
         work_log)
```

All LLM calls route through the external LiteLLM proxy.

---

## Persona Types

| Type       | Purpose                                    | Triggered by              |
|------------|--------------------------------------------|---------------------------|
| Observer   | Watches sources, creates tickets           | Cron, events, webhooks    |
| Solver     | Picks up tickets, does the work            | New matching ticket       |
| Reviewer   | Validates solved work, approves or rejects | Ticket moved to "review"  |
| Manager    | Prioritizes, delegates, hires/fires        | Escalations, overload     |

### Persona Schema

```python
persona = {
    "id": "security-analyst",
    "name": "Sarah Chen",
    "role": "Security Analyst",
    "type": "observer",
    "reports_to": "vp-engineering",
    "skills": ["security", "code-review", "compliance"],
    "watches": [
        {"source": "git_repo", "path": "/src/**", "schedule": "every 6h"},
        {"source": "docs", "path": "/docs/infra/**", "on": "change"},
    ],
    "picks_up": [],
    "tools": ["read_file", "grep_code", "search_web", "create_ticket"],
    "model_id": "azure/gpt-5",
    "backstory": "Senior security engineer with 10 years experience...",
    "status": "active",
}
```

---

## Task Board

Central coordination between observers and solvers.

### Ticket Lifecycle

```
  open -> assigned -> in_progress -> review -> done
                                       |
                                       v
                                    rejected -> open (reassigned)
```

### Ticket Schema

```sql
tickets
  id            serial PK
  title         text
  description   text
  priority      text           -- critical | high | medium | low
  status        text           -- open | assigned | in_progress | review | done | rejected
  tags          jsonb          -- ["security", "backend"]
  created_by    text FK        -- persona id
  assigned_to   text FK        -- persona id (nullable)
  reviewed_by   text FK        -- persona id (nullable)
  context       jsonb          -- files, code snippets, references
  result        text           -- solver's output / solution
  parent_id     int FK         -- for sub-tickets
  created_at    timestamp
  updated_at    timestamp
```

### Auto-Assignment

When a ticket is created:
1. Event bus publishes `ticket.created`
2. Solvers with matching skills are candidates
3. Solver with lowest current workload auto-claims
4. Manager can override assignment

---

## Event System

Three entry points for work:

### 1. Chat Messages
User sends message via Telegram/Slack. Gateway routes to bound persona
via bindings (channel + peer matching, like OpenClaw). Persona executes,
may create tickets.

### 2. Scheduled Triggers (Observers)
APScheduler fires cron jobs per observer's `watches` config. Publishes
event to Redis. Agent Runner spins up the observer persona with Strands.
Persona scans sources, creates tickets if issues found.

### 3. External Events (Webhooks)
GitHub push, alerting systems, etc. Gateway receives webhook, publishes
typed event to Redis. Observers watching that source type get triggered.

### Bindings (from OpenClaw)

```yaml
bindings:
  - persona_id: "ceo"
    match: { channel: "telegram", chat_type: "direct" }
  - persona_id: "support-lead"
    match: { channel: "telegram", chat_type: "group" }
  - persona_id: "ceo"  # fallback
```

---

## Dynamic Hiring

Manager personas have access to `hire_persona` and `fire_persona` tools.

```python
@tool
def hire_persona(name, role, type, skills, backstory, reports_to):
    """Create a new persona in the company."""
    # Validates org chart constraints
    # Inserts into DB
    # Creates workspace directory
    # Registers with scheduler if observer
    # Returns confirmation

@tool
def fire_persona(persona_id, reason):
    """Deactivate a persona. Reassigns their open tickets."""
```

Trigger: Manager notices overload (e.g., >10 unassigned tickets in a
skill area) or a gap in coverage for a new domain.

---

## Memory & Persistence

### Per-Persona Memory (PostgreSQL)

```sql
persona_memory
  id            serial PK
  persona_id    text FK
  type          text     -- fact | decision | interaction | preference
  content       text
  related_to    text     -- other persona id (nullable)
  created_at    timestamp
```

### Work History (Performance Tracking)

```sql
work_log
  id            serial PK
  persona_id    text FK
  ticket_id     int FK
  action        text     -- created | picked_up | solved | reviewed | rejected
  details       text
  duration_sec  int
  created_at    timestamp
```

### Sessions (like OpenClaw)

Per-channel, per-peer JSONL files stored in each persona's workspace.
Compacted when token count grows too large (summarize old messages).

---

## Tech Stack

| Component      | Technology               | Why                              |
|----------------|--------------------------|----------------------------------|
| Gateway/API    | FastAPI                  | Async, WebSocket, fast           |
| Agent runtime  | Strands Agents SDK       | @tool, A2A, native LiteLLM      |
| LLM provider   | LiteLLM proxy (external) | Your existing proxy              |
| Database       | PostgreSQL               | Relational data, JSONB support   |
| Event bus      | Redis                    | Pub/sub, job queue, locks        |
| Scheduler      | APScheduler              | Observer cron triggers           |
| Chat           | python-telegram-bot      | Extensible to Slack/Discord      |
| Workspaces     | Filesystem (volumes)     | Per-persona isolation            |
| Deployment     | Docker Compose           | Self-hosted, reproducible        |

---

## Project Structure

```
opencompany/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── src/
│   └── opencompany/
│       ├── main.py                  # FastAPI app entrypoint
│       ├── gateway/
│       │   ├── api.py               # REST routes
│       │   ├── ws.py                # WebSocket handler
│       │   └── channels/
│       │       ├── base.py          # Channel adapter interface
│       │       ├── telegram.py      # Telegram adapter
│       │       └── webhook.py       # Generic webhook receiver
│       ├── company/
│       │   ├── engine.py            # Company orchestration
│       │   ├── personas.py          # Persona CRUD, org chart
│       │   ├── taskboard.py         # Ticket lifecycle
│       │   └── scheduler.py         # Cron triggers
│       ├── agents/
│       │   ├── runner.py            # Strands agent execution
│       │   ├── tools/
│       │   │   ├── tickets.py       # create_ticket, update_ticket
│       │   │   ├── code.py          # read_file, grep_code, git_diff
│       │   │   ├── web.py           # search_web, fetch_url
│       │   │   └── company.py       # hire_persona, fire_persona
│       │   └── prompts.py           # System prompt builder
│       ├── models/
│       │   └── db.py                # SQLAlchemy models
│       └── events/
│           └── bus.py               # Redis pub/sub
├── workspaces/                      # Per-persona dirs (volume)
├── config/
│   └── company.yaml                 # Initial org chart
└── migrations/                      # Alembic
```

---

## Example Workflow: Security Scan

1. **Cron fires** (every 6h) -> triggers `security-analyst` persona
2. **Security Analyst** (observer) spins up via Strands with tools:
   `read_file`, `grep_code`, `create_ticket`
3. Analyst scans `/src/**` for patterns (SQL injection, hardcoded secrets, etc.)
4. Finds issue -> calls `create_ticket(priority="critical", title="SQL injection in auth.py", tags=["security","backend"], context={file, line, snippet})`
5. **Event bus** publishes `ticket.created`
6. **Security Engineer** (solver) with skills `["security"]` auto-claims ticket
7. Engineer reads ticket context, writes fix using `edit_file` tool, commits
8. Moves ticket to `review`
9. **Security Analyst** reviews the fix, approves -> ticket `done`
10. All actions logged to `work_log` for performance tracking

---

## OpenClaw Mapping

| OpenClaw             | OpenCompany                           |
|----------------------|---------------------------------------|
| Gateway              | FastAPI gateway (REST + WS + channels)|
| Agent sessions       | Per-persona sessions (JSONL)          |
| Bindings             | Bindings + org chart routing          |
| Workspaces           | Per-persona workspace dirs            |
| Skills               | @tool functions, per-persona toolsets |
| Multi-agent config   | company.yaml org chart                |
| Memory               | PostgreSQL persona_memory + workspace |
| Canvas               | Task board (API-first, UI later)      |
| SOUL.md              | Per-persona backstory + role prompt   |
