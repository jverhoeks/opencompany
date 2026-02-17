# OpenCompany Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a virtual AI company where agent personas (observers, solvers, reviewers, managers) autonomously coordinate work through a task board, triggered by chat, events, and schedules.

**Architecture:** FastAPI gateway routes work into a Company Engine backed by Strands Agents SDK + LiteLLM. Personas persist in PostgreSQL, communicate via Redis pub/sub, and operate in isolated workspaces. Modeled after OpenClaw's gateway pattern.

**Tech Stack:** Python 3.13, Strands Agents SDK, LiteLLM, FastAPI, PostgreSQL, Redis, APScheduler, Docker Compose

**Design doc:** `docs/plans/2026-02-17-opencompany-design.md`

---

## Task 1: Project Scaffolding

**Files:**
- Create: `opencompany/pyproject.toml`
- Create: `opencompany/src/opencompany/__init__.py`
- Create: `opencompany/src/opencompany/main.py`
- Create: `opencompany/.env.example`

**Step 1: Create pyproject.toml**

```toml
[project]
name = "opencompany"
version = "0.1.0"
description = "Virtual AI company — autonomous agent personas coordinating via task board"
requires-python = ">=3.11"
dependencies = [
    "strands-agents>=0.3.0",
    "strands-agents-tools>=0.1.0",
    "litellm>=1.75.0",
    "fastapi>=0.115.0",
    "uvicorn>=0.34.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "asyncpg>=0.30.0",
    "alembic>=1.15.0",
    "redis>=5.0.0",
    "apscheduler>=3.11.0",
    "python-telegram-bot>=22.0",
    "python-dotenv>=1.0.0",
    "pyyaml>=6.0",
    "httpx>=0.28.0",
]

[project.scripts]
opencompany = "opencompany.main:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

**Step 2: Create minimal main.py**

```python
import uvicorn
from fastapi import FastAPI

app = FastAPI(title="OpenCompany", version="0.1.0")


@app.get("/health")
async def health():
    return {"status": "ok"}


def main():
    uvicorn.run("opencompany.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
```

**Step 3: Create .env.example**

```
OPENAI_API_KEY=your-litellm-proxy-key
OPENAI_API_BASE=https://your-litellm-proxy.example.com
LITELLM_MODEL_ID=azure/gpt-5

DATABASE_URL=postgresql+asyncpg://opencompany:opencompany@localhost:5432/opencompany
REDIS_URL=redis://localhost:6379/0

TELEGRAM_BOT_TOKEN=your-telegram-bot-token
```

**Step 4: Create __init__.py (empty)**

**Step 5: Verify it runs**

Run: `cd opencompany && uv run opencompany`
Expected: FastAPI starts on port 8000, `GET /health` returns `{"status": "ok"}`

**Step 6: Commit**

```bash
git add opencompany/
git commit -m "feat: project scaffolding with FastAPI entrypoint"
```

---

## Task 2: Docker Compose (Postgres + Redis + App)

**Files:**
- Create: `opencompany/docker-compose.yml`
- Create: `opencompany/Dockerfile`

**Step 1: Create docker-compose.yml**

```yaml
services:
  db:
    image: postgres:17-alpine
    environment:
      POSTGRES_USER: opencompany
      POSTGRES_PASSWORD: opencompany
      POSTGRES_DB: opencompany
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  app:
    build: .
    ports:
      - "8000:8000"
    env_file: .env
    depends_on:
      - db
      - redis
    volumes:
      - ./workspaces:/app/workspaces
      - ./config:/app/config

volumes:
  pgdata:
```

**Step 2: Create Dockerfile**

```dockerfile
FROM python:3.13-slim

WORKDIR /app
RUN pip install uv

COPY pyproject.toml .
RUN uv pip install --system -e .

COPY src/ src/
COPY config/ config/

CMD ["uvicorn", "opencompany.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Step 3: Verify infra starts**

Run: `docker compose up db redis -d`
Expected: Postgres on 5432, Redis on 6379

**Step 4: Commit**

```bash
git add docker-compose.yml Dockerfile
git commit -m "feat: docker compose with postgres and redis"
```

---

## Task 3: Database Models (SQLAlchemy)

**Files:**
- Create: `opencompany/src/opencompany/models/__init__.py`
- Create: `opencompany/src/opencompany/models/db.py`
- Create: `opencompany/src/opencompany/models/base.py`
- Test: `opencompany/tests/test_models.py`

**Step 1: Write test for models**

```python
# tests/test_models.py
from opencompany.models.db import Persona, Ticket, WorkLog, PersonaMemory


def test_persona_creation():
    p = Persona(
        id="security-analyst",
        name="Sarah Chen",
        role="Security Analyst",
        type="observer",
        skills=["security", "code-review"],
        backstory="Senior security engineer.",
        status="active",
    )
    assert p.id == "security-analyst"
    assert p.type == "observer"
    assert "security" in p.skills


def test_ticket_creation():
    t = Ticket(
        title="SQL injection in auth.py",
        priority="critical",
        status="open",
        tags=["security", "backend"],
        created_by="security-analyst",
    )
    assert t.status == "open"
    assert t.priority == "critical"
```

**Step 2: Run test to verify it fails**

Run: `cd opencompany && uv run pytest tests/test_models.py -v`
Expected: FAIL — ImportError

**Step 3: Create base.py**

```python
# src/opencompany/models/base.py
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass


class Base(DeclarativeBase, MappedAsDataclass):
    pass
```

**Step 4: Create db.py with all models**

```python
# src/opencompany/models/db.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opencompany.models.base import Base


class Persona(Base):
    __tablename__ = "personas"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    role: Mapped[str]
    type: Mapped[str]  # observer | solver | reviewer | manager
    reports_to: Mapped[Optional[str]] = mapped_column(
        ForeignKey("personas.id"), default=None
    )
    skills: Mapped[list] = mapped_column(JSONB, default_factory=list)
    watches: Mapped[list] = mapped_column(JSONB, default_factory=list)
    picks_up: Mapped[list] = mapped_column(JSONB, default_factory=list)
    tools: Mapped[list] = mapped_column(JSONB, default_factory=list)
    model_id: Mapped[Optional[str]] = mapped_column(default=None)
    backstory: Mapped[str] = mapped_column(default="")
    status: Mapped[str] = mapped_column(default="active")
    created_by: Mapped[Optional[str]] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True, init=False, autoincrement=True)
    title: Mapped[str]
    description: Mapped[str] = mapped_column(default="")
    priority: Mapped[str] = mapped_column(default="medium")
    status: Mapped[str] = mapped_column(default="open")
    tags: Mapped[list] = mapped_column(JSONB, default_factory=list)
    created_by: Mapped[str] = mapped_column(default="")
    assigned_to: Mapped[Optional[str]] = mapped_column(default=None)
    reviewed_by: Mapped[Optional[str]] = mapped_column(default=None)
    context: Mapped[dict] = mapped_column(JSONB, default_factory=dict)
    result: Mapped[Optional[str]] = mapped_column(default=None)
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tickets.id"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        default_factory=lambda: datetime.now(timezone.utc),
        onupdate=func.now(),
    )


class PersonaMemory(Base):
    __tablename__ = "persona_memory"

    id: Mapped[int] = mapped_column(primary_key=True, init=False, autoincrement=True)
    persona_id: Mapped[str] = mapped_column(ForeignKey("personas.id"))
    type: Mapped[str]  # fact | decision | interaction | preference
    content: Mapped[str]
    related_to: Mapped[Optional[str]] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class WorkLog(Base):
    __tablename__ = "work_log"

    id: Mapped[int] = mapped_column(primary_key=True, init=False, autoincrement=True)
    persona_id: Mapped[str] = mapped_column(ForeignKey("personas.id"))
    ticket_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tickets.id"), default=None
    )
    action: Mapped[str]  # created | picked_up | solved | reviewed | rejected
    details: Mapped[str] = mapped_column(default="")
    duration_sec: Mapped[Optional[int]] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(primary_key=True)
    channel: Mapped[str]  # telegram | slack | webhook
    peer: Mapped[str]
    persona_id: Mapped[str] = mapped_column(ForeignKey("personas.id"))
    transcript_path: Mapped[str] = mapped_column(default="")
    created_at: Mapped[datetime] = mapped_column(
        default_factory=lambda: datetime.now(timezone.utc)
    )
```

**Step 5: Create __init__.py**

```python
# src/opencompany/models/__init__.py
from opencompany.models.db import Persona, Ticket, PersonaMemory, WorkLog, Session
from opencompany.models.base import Base
```

**Step 6: Run tests**

Run: `cd opencompany && uv run pytest tests/test_models.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add src/opencompany/models/ tests/test_models.py
git commit -m "feat: SQLAlchemy models for personas, tickets, memory, work log"
```

---

## Task 4: Database Connection & Alembic Migrations

**Files:**
- Create: `opencompany/src/opencompany/models/engine.py`
- Modify: `opencompany/src/opencompany/main.py` — add DB startup
- Create: `opencompany/alembic.ini` + `opencompany/migrations/`

**Step 1: Create engine.py**

```python
# src/opencompany/models/engine.py
import os

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://opencompany:opencompany@localhost:5432/opencompany",
)

engine = create_async_engine(DATABASE_URL)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def get_session():
    async with async_session() as session:
        yield session
```

**Step 2: Add lifespan to main.py for table creation (dev mode)**

```python
# src/opencompany/main.py
import uvicorn
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI

from opencompany.models.base import Base
from opencompany.models.engine import engine
import opencompany.models.db  # noqa: F401 — register models

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title="OpenCompany", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


def main():
    uvicorn.run("opencompany.main:app", host="0.0.0.0", port=8000, reload=True)
```

**Step 3: Initialize Alembic**

Run: `cd opencompany && uv run alembic init migrations`
Then edit `alembic.ini` to set `sqlalchemy.url` and `migrations/env.py` to import `Base.metadata`.

**Step 4: Verify tables create**

Run: `docker compose up db -d && cd opencompany && uv run opencompany`
Then: `psql postgresql://opencompany:opencompany@localhost:5432/opencompany -c '\dt'`
Expected: Tables personas, tickets, persona_memory, work_log, sessions

**Step 5: Commit**

```bash
git add src/opencompany/models/engine.py src/opencompany/main.py alembic.ini migrations/
git commit -m "feat: async DB engine, table creation on startup"
```

---

## Task 5: Agent Runner (Strands + LiteLLM)

**Files:**
- Create: `opencompany/src/opencompany/agents/__init__.py`
- Create: `opencompany/src/opencompany/agents/runner.py`
- Create: `opencompany/src/opencompany/agents/prompts.py`
- Test: `opencompany/tests/test_runner.py`

**Step 1: Write test**

```python
# tests/test_runner.py
from opencompany.agents.prompts import build_system_prompt
from opencompany.models.db import Persona


def test_build_system_prompt():
    p = Persona(
        id="security-analyst",
        name="Sarah Chen",
        role="Security Analyst",
        type="observer",
        skills=["security"],
        backstory="Senior security engineer with 10 years experience.",
    )
    prompt = build_system_prompt(p)
    assert "Sarah Chen" in prompt
    assert "Security Analyst" in prompt
    assert "observer" in prompt
    assert "Senior security engineer" in prompt
```

**Step 2: Run test — expect FAIL**

**Step 3: Create prompts.py**

```python
# src/opencompany/agents/prompts.py
from opencompany.models.db import Persona


def build_system_prompt(persona: Persona) -> str:
    return f"""You are {persona.name}, a {persona.role} at OpenCompany.

Your persona type is: {persona.type}
Your skills: {', '.join(persona.skills)}

Backstory: {persona.backstory}

RULES:
- You act autonomously as your role demands.
- If you are an OBSERVER: scan sources, find issues, create tickets.
- If you are a SOLVER: pick up assigned tickets, do the work, submit for review.
- If you are a REVIEWER: validate solutions, approve or reject with feedback.
- If you are a MANAGER: delegate, prioritize, hire/fire as needed.
- Always use tools to take action. Do not just describe what you would do.
- Be concise and direct.
"""
```

**Step 4: Create runner.py**

```python
# src/opencompany/agents/runner.py
import os

from strands import Agent
from strands.models.litellm import LiteLLMModel

from opencompany.agents.prompts import build_system_prompt
from opencompany.models.db import Persona

# Tool registry — maps tool names to actual tool functions
_TOOL_REGISTRY: dict = {}


def register_tool(name: str, func):
    """Register a tool function by name."""
    _TOOL_REGISTRY[name] = func


def get_model() -> LiteLLMModel:
    """Create LiteLLM model pointing at the proxy."""
    return LiteLLMModel(
        client_args={
            "api_key": os.environ.get("OPENAI_API_KEY", ""),
            "api_base": os.environ.get("OPENAI_API_BASE", ""),
            "use_litellm_proxy": True,
        },
        model_id=os.environ.get("LITELLM_MODEL_ID", "azure/gpt-5"),
    )


def create_agent(persona: Persona, extra_tools: list | None = None) -> Agent:
    """Spin up a Strands agent for a persona."""
    tools = []
    for tool_name in persona.tools:
        if tool_name in _TOOL_REGISTRY:
            tools.append(_TOOL_REGISTRY[tool_name])

    if extra_tools:
        tools.extend(extra_tools)

    model = get_model()
    if persona.model_id:
        model = LiteLLMModel(
            client_args={
                "api_key": os.environ.get("OPENAI_API_KEY", ""),
                "api_base": os.environ.get("OPENAI_API_BASE", ""),
                "use_litellm_proxy": True,
            },
            model_id=persona.model_id,
        )

    return Agent(
        model=model,
        system_prompt=build_system_prompt(persona),
        tools=tools,
        name=persona.name,
        description=f"{persona.role} ({persona.type})",
    )


async def run_persona(persona: Persona, task: str) -> str:
    """Run a persona agent with a task and return the result."""
    agent = create_agent(persona)
    result = agent(task)
    return str(result)
```

**Step 5: Run tests**

Run: `cd opencompany && uv run pytest tests/test_runner.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/opencompany/agents/ tests/test_runner.py
git commit -m "feat: agent runner with Strands SDK + LiteLLM proxy"
```

---

## Task 6: Core Tools (Tickets + Code + Company)

**Files:**
- Create: `opencompany/src/opencompany/agents/tools/__init__.py`
- Create: `opencompany/src/opencompany/agents/tools/tickets.py`
- Create: `opencompany/src/opencompany/agents/tools/code.py`
- Create: `opencompany/src/opencompany/agents/tools/company.py`
- Test: `opencompany/tests/test_tools.py`

**Step 1: Write test for ticket tools**

```python
# tests/test_tools.py
import pytest
from unittest.mock import AsyncMock, patch


def test_ticket_tool_schema():
    """Verify ticket tools have correct signatures."""
    from opencompany.agents.tools.tickets import create_ticket, list_tickets

    # Strands @tool functions should be callable
    assert callable(create_ticket)
    assert callable(list_tickets)
```

**Step 2: Run test — expect FAIL**

**Step 3: Create tickets.py**

```python
# src/opencompany/agents/tools/tickets.py
from strands import tool


@tool
def create_ticket(
    title: str,
    description: str,
    priority: str = "medium",
    tags: str = "",
    context: str = "",
) -> str:
    """Create a new ticket on the task board.

    Args:
        title: Short title describing the issue or task
        description: Detailed description of what needs to be done
        priority: One of: critical, high, medium, low
        tags: Comma-separated tags (e.g. "security,backend")
        context: Relevant file paths, code snippets, or references
    """
    # Import here to avoid circular deps — DB write happens via engine
    from opencompany.company.taskboard import create_ticket_sync

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    context_dict = {"raw": context} if context else {}

    ticket_id = create_ticket_sync(
        title=title,
        description=description,
        priority=priority,
        tags=tag_list,
        context=context_dict,
        created_by="agent",  # overridden by runner with persona id
    )
    return f"Ticket #{ticket_id} created: {title} [{priority}]"


@tool
def list_tickets(status: str = "open", tags: str = "") -> str:
    """List tickets from the task board.

    Args:
        status: Filter by status (open, assigned, in_progress, review, done)
        tags: Comma-separated tags to filter by
    """
    from opencompany.company.taskboard import list_tickets_sync

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    tickets = list_tickets_sync(status=status, tags=tag_list)
    if not tickets:
        return f"No tickets with status={status}"
    lines = [f"#{t['id']} [{t['priority']}] {t['title']} (-> {t['assigned_to'] or 'unassigned'})" for t in tickets]
    return "\n".join(lines)


@tool
def update_ticket(ticket_id: int, status: str = "", result: str = "") -> str:
    """Update a ticket's status or add a result.

    Args:
        ticket_id: The ticket ID to update
        status: New status (assigned, in_progress, review, done, rejected)
        result: Solution or output to attach to the ticket
    """
    from opencompany.company.taskboard import update_ticket_sync

    update_ticket_sync(ticket_id=ticket_id, status=status or None, result=result or None)
    return f"Ticket #{ticket_id} updated"
```

**Step 4: Create code.py**

```python
# src/opencompany/agents/tools/code.py
import os
import subprocess

from strands import tool


@tool
def read_file(path: str) -> str:
    """Read the contents of a file.

    Args:
        path: Path to the file to read
    """
    if not os.path.isfile(path):
        return f"Error: {path} not found"
    with open(path) as f:
        return f.read()


@tool
def grep_code(pattern: str, directory: str = ".", file_glob: str = "*.py") -> str:
    """Search for a pattern in code files.

    Args:
        pattern: Regex pattern to search for
        directory: Directory to search in
        file_glob: File glob pattern to match (e.g. *.py, *.yaml)
    """
    try:
        result = subprocess.run(
            ["grep", "-rn", "--include", file_glob, pattern, directory],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout[:5000] if result.stdout else "No matches found"
    except Exception as e:
        return f"Error: {e}"


@tool
def list_files(directory: str = ".", pattern: str = "") -> str:
    """List files in a directory.

    Args:
        directory: Directory to list
        pattern: Optional glob pattern to filter files
    """
    import glob as glob_mod

    if pattern:
        files = glob_mod.glob(os.path.join(directory, pattern), recursive=True)
    else:
        files = os.listdir(directory)
    return "\n".join(sorted(files)[:100])
```

**Step 5: Create company.py (hire/fire)**

```python
# src/opencompany/agents/tools/company.py
from strands import tool


@tool
def hire_persona(
    persona_id: str,
    name: str,
    role: str,
    persona_type: str,
    skills: str,
    backstory: str,
    reports_to: str = "",
) -> str:
    """Hire a new persona (create a new agent in the company).

    Args:
        persona_id: Unique ID for the persona (e.g. "junior-security-eng")
        name: Human name (e.g. "Alex Rivera")
        role: Job title (e.g. "Junior Security Engineer")
        persona_type: One of: observer, solver, reviewer, manager
        skills: Comma-separated skills (e.g. "security,python")
        backstory: Personality and background description
        reports_to: ID of the manager persona (optional)
    """
    from opencompany.company.personas import hire_persona_sync

    skill_list = [s.strip() for s in skills.split(",") if s.strip()]
    result = hire_persona_sync(
        persona_id=persona_id,
        name=name,
        role=role,
        persona_type=persona_type,
        skills=skill_list,
        backstory=backstory,
        reports_to=reports_to or None,
    )
    return result


@tool
def fire_persona(persona_id: str, reason: str = "") -> str:
    """Deactivate a persona and reassign their open tickets.

    Args:
        persona_id: ID of the persona to deactivate
        reason: Reason for deactivation
    """
    from opencompany.company.personas import fire_persona_sync

    return fire_persona_sync(persona_id=persona_id, reason=reason)


@tool
def list_team(reports_to: str = "") -> str:
    """List active personas in the company.

    Args:
        reports_to: Filter by manager ID (optional, empty = all)
    """
    from opencompany.company.personas import list_personas_sync

    personas = list_personas_sync(reports_to=reports_to or None)
    if not personas:
        return "No active personas found"
    lines = [f"- {p['name']} ({p['role']}) [{p['type']}] skills={p['skills']}" for p in personas]
    return "\n".join(lines)
```

**Step 6: Create __init__.py that registers all tools**

```python
# src/opencompany/agents/tools/__init__.py
from opencompany.agents.tools.tickets import create_ticket, list_tickets, update_ticket
from opencompany.agents.tools.code import read_file, grep_code, list_files
from opencompany.agents.tools.company import hire_persona, fire_persona, list_team

ALL_TOOLS = {
    "create_ticket": create_ticket,
    "list_tickets": list_tickets,
    "update_ticket": update_ticket,
    "read_file": read_file,
    "grep_code": grep_code,
    "list_files": list_files,
    "hire_persona": hire_persona,
    "fire_persona": fire_persona,
    "list_team": list_team,
}
```

**Step 7: Run tests**

Run: `cd opencompany && uv run pytest tests/test_tools.py -v`
Expected: PASS

**Step 8: Commit**

```bash
git add src/opencompany/agents/tools/ tests/test_tools.py
git commit -m "feat: core tools — tickets, code, company (hire/fire)"
```

---

## Task 7: Company Engine — Personas & Task Board

**Files:**
- Create: `opencompany/src/opencompany/company/__init__.py`
- Create: `opencompany/src/opencompany/company/personas.py`
- Create: `opencompany/src/opencompany/company/taskboard.py`
- Test: `opencompany/tests/test_taskboard.py`

**Step 1: Write test**

```python
# tests/test_taskboard.py
from opencompany.company.taskboard import (
    find_best_solver,
)


def test_find_best_solver_matches_skills():
    solvers = [
        {"id": "backend-dev", "skills": ["python", "backend"], "workload": 3},
        {"id": "security-eng", "skills": ["security", "python"], "workload": 1},
    ]
    best = find_best_solver(tags=["security"], solvers=solvers)
    assert best["id"] == "security-eng"


def test_find_best_solver_prefers_lower_workload():
    solvers = [
        {"id": "dev-1", "skills": ["python"], "workload": 5},
        {"id": "dev-2", "skills": ["python"], "workload": 2},
    ]
    best = find_best_solver(tags=["python"], solvers=solvers)
    assert best["id"] == "dev-2"


def test_find_best_solver_no_match():
    solvers = [
        {"id": "dev-1", "skills": ["python"], "workload": 1},
    ]
    best = find_best_solver(tags=["rust"], solvers=solvers)
    assert best is None
```

**Step 2: Run test — expect FAIL**

**Step 3: Create taskboard.py**

```python
# src/opencompany/company/taskboard.py
"""Task board: ticket lifecycle, auto-assignment, sync wrappers for tool use."""
import asyncio
from typing import Optional

from sqlalchemy import select

from opencompany.models.db import Ticket, Persona
from opencompany.models.engine import async_session


def find_best_solver(
    tags: list[str], solvers: list[dict]
) -> Optional[dict]:
    """Find the best solver for a ticket based on skill overlap and workload."""
    candidates = []
    for solver in solvers:
        overlap = len(set(solver["skills"]) & set(tags))
        if overlap > 0:
            candidates.append((overlap, solver["workload"], solver))

    if not candidates:
        return None

    # Sort by skill overlap (desc), then workload (asc)
    candidates.sort(key=lambda x: (-x[0], x[1]))
    return candidates[0][2]


async def _create_ticket(
    title: str,
    description: str,
    priority: str,
    tags: list,
    context: dict,
    created_by: str,
) -> int:
    async with async_session() as session:
        ticket = Ticket(
            title=title,
            description=description,
            priority=priority,
            tags=tags,
            context=context,
            created_by=created_by,
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        return ticket.id


def create_ticket_sync(**kwargs) -> int:
    return asyncio.get_event_loop().run_until_complete(_create_ticket(**kwargs))


async def _list_tickets(status: str, tags: list) -> list[dict]:
    async with async_session() as session:
        q = select(Ticket).where(Ticket.status == status)
        result = await session.execute(q)
        tickets = result.scalars().all()
        if tags:
            tickets = [t for t in tickets if set(tags) & set(t.tags)]
        return [
            {"id": t.id, "title": t.title, "priority": t.priority, "assigned_to": t.assigned_to, "tags": t.tags}
            for t in tickets
        ]


def list_tickets_sync(**kwargs) -> list[dict]:
    return asyncio.get_event_loop().run_until_complete(_list_tickets(**kwargs))


async def _update_ticket(
    ticket_id: int, status: Optional[str] = None, result: Optional[str] = None
):
    async with async_session() as session:
        ticket = await session.get(Ticket, ticket_id)
        if not ticket:
            return
        if status:
            ticket.status = status
        if result:
            ticket.result = result
        await session.commit()


def update_ticket_sync(**kwargs):
    asyncio.get_event_loop().run_until_complete(_update_ticket(**kwargs))
```

**Step 4: Create personas.py**

```python
# src/opencompany/company/personas.py
"""Persona management: CRUD, org chart, sync wrappers for tool use."""
import asyncio
import os
from typing import Optional

from sqlalchemy import select

from opencompany.models.db import Persona
from opencompany.models.engine import async_session


async def _hire_persona(
    persona_id: str,
    name: str,
    role: str,
    persona_type: str,
    skills: list[str],
    backstory: str,
    reports_to: Optional[str] = None,
) -> str:
    async with async_session() as session:
        existing = await session.get(Persona, persona_id)
        if existing:
            return f"Error: persona '{persona_id}' already exists"

        persona = Persona(
            id=persona_id,
            name=name,
            role=role,
            type=persona_type,
            skills=skills,
            backstory=backstory,
            reports_to=reports_to,
        )
        session.add(persona)
        await session.commit()

    # Create workspace directory
    workspace = os.path.join("workspaces", persona_id)
    os.makedirs(workspace, exist_ok=True)

    return f"Hired {name} as {role} (id={persona_id})"


def hire_persona_sync(**kwargs) -> str:
    return asyncio.get_event_loop().run_until_complete(_hire_persona(**kwargs))


async def _fire_persona(persona_id: str, reason: str = "") -> str:
    async with async_session() as session:
        persona = await session.get(Persona, persona_id)
        if not persona:
            return f"Error: persona '{persona_id}' not found"
        persona.status = "terminated"
        await session.commit()
        return f"Terminated {persona.name} ({persona_id}). Reason: {reason}"


def fire_persona_sync(**kwargs) -> str:
    return asyncio.get_event_loop().run_until_complete(_fire_persona(**kwargs))


async def _list_personas(reports_to: Optional[str] = None) -> list[dict]:
    async with async_session() as session:
        q = select(Persona).where(Persona.status == "active")
        if reports_to:
            q = q.where(Persona.reports_to == reports_to)
        result = await session.execute(q)
        return [
            {"id": p.id, "name": p.name, "role": p.role, "type": p.type, "skills": p.skills}
            for p in result.scalars().all()
        ]


def list_personas_sync(**kwargs) -> list[dict]:
    return asyncio.get_event_loop().run_until_complete(_list_personas(**kwargs))
```

**Step 5: Create __init__.py**

```python
# src/opencompany/company/__init__.py
```

**Step 6: Run tests**

Run: `cd opencompany && uv run pytest tests/test_taskboard.py -v`
Expected: PASS (find_best_solver is pure logic, no DB)

**Step 7: Commit**

```bash
git add src/opencompany/company/ tests/test_taskboard.py
git commit -m "feat: company engine — personas CRUD, task board with auto-assignment"
```

---

## Task 8: Event Bus (Redis Pub/Sub)

**Files:**
- Create: `opencompany/src/opencompany/events/__init__.py`
- Create: `opencompany/src/opencompany/events/bus.py`

**Step 1: Create bus.py**

```python
# src/opencompany/events/bus.py
import json
import os
from typing import Callable

import redis.asyncio as redis

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

_redis: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis


async def publish(event_type: str, data: dict):
    """Publish an event to the bus."""
    r = await get_redis()
    payload = json.dumps({"type": event_type, "data": data})
    await r.publish("opencompany:events", payload)


async def subscribe(callback: Callable):
    """Subscribe to all events. Calls callback(event_type, data) for each."""
    r = await get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe("opencompany:events")

    async for message in pubsub.listen():
        if message["type"] == "message":
            payload = json.loads(message["data"])
            await callback(payload["type"], payload["data"])
```

**Step 2: Commit**

```bash
git add src/opencompany/events/
git commit -m "feat: Redis pub/sub event bus"
```

---

## Task 9: Scheduler (Observer Cron Triggers)

**Files:**
- Create: `opencompany/src/opencompany/company/scheduler.py`

**Step 1: Create scheduler.py**

```python
# src/opencompany/company/scheduler.py
"""Schedules observer personas to run on cron triggers."""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from opencompany.agents.runner import run_persona
from opencompany.models.db import Persona
from opencompany.models.engine import async_session

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _run_observer(persona_id: str, watch: dict):
    """Run an observer persona for a specific watch config."""
    async with async_session() as session:
        persona = await session.get(Persona, persona_id)
        if not persona or persona.status != "active":
            return

    source = watch.get("source", "unknown")
    path = watch.get("path", ".")
    task = f"Scan {source} at {path}. Find issues and create tickets for anything noteworthy."

    logger.info(f"Running observer {persona_id}: {task}")
    try:
        result = await run_persona(persona, task)
        logger.info(f"Observer {persona_id} finished: {result[:200]}")
    except Exception as e:
        logger.error(f"Observer {persona_id} failed: {e}")


def _parse_schedule(schedule_str: str) -> dict:
    """Parse schedule string like 'every 6h' or 'every 30m' to APScheduler kwargs."""
    s = schedule_str.lower().strip()
    if s.startswith("every "):
        val = s[6:]
        if val.endswith("h"):
            return {"trigger": "interval", "hours": int(val[:-1])}
        elif val.endswith("m"):
            return {"trigger": "interval", "minutes": int(val[:-1])}
        elif val.endswith("d"):
            return {"trigger": "interval", "days": int(val[:-1])}
    return {"trigger": "interval", "hours": 1}


async def register_observers():
    """Load all active observer personas and register their cron jobs."""
    async with async_session() as session:
        q = select(Persona).where(Persona.type == "observer", Persona.status == "active")
        result = await session.execute(q)
        observers = result.scalars().all()

    for persona in observers:
        for watch in persona.watches:
            schedule = watch.get("schedule", "every 1h")
            kwargs = _parse_schedule(schedule)
            job_id = f"{persona.id}:{watch.get('source', 'default')}"
            scheduler.add_job(
                _run_observer,
                id=job_id,
                replace_existing=True,
                args=[persona.id, watch],
                **kwargs,
            )
            logger.info(f"Scheduled observer {job_id} ({schedule})")


def start_scheduler():
    scheduler.start()
```

**Step 2: Commit**

```bash
git add src/opencompany/company/scheduler.py
git commit -m "feat: APScheduler cron triggers for observer personas"
```

---

## Task 10: Gateway REST API

**Files:**
- Create: `opencompany/src/opencompany/gateway/__init__.py`
- Create: `opencompany/src/opencompany/gateway/api.py`
- Modify: `opencompany/src/opencompany/main.py` — mount routes

**Step 1: Create api.py**

```python
# src/opencompany/gateway/api.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opencompany.models.db import Persona, Ticket
from opencompany.models.engine import get_session
from opencompany.agents.runner import run_persona

router = APIRouter()


# --- Persona endpoints ---

class PersonaOut(BaseModel):
    id: str
    name: str
    role: str
    type: str
    skills: list
    status: str

    model_config = {"from_attributes": True}


@router.get("/personas", response_model=list[PersonaOut])
async def list_personas(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Persona).where(Persona.status == "active"))
    return result.scalars().all()


@router.get("/personas/{persona_id}", response_model=PersonaOut)
async def get_persona(persona_id: str, session: AsyncSession = Depends(get_session)):
    persona = await session.get(Persona, persona_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    return persona


# --- Ticket endpoints ---

class TicketOut(BaseModel):
    id: int
    title: str
    priority: str
    status: str
    tags: list
    created_by: str
    assigned_to: str | None

    model_config = {"from_attributes": True}


class TicketCreate(BaseModel):
    title: str
    description: str = ""
    priority: str = "medium"
    tags: list[str] = []
    context: dict = {}


@router.get("/tickets", response_model=list[TicketOut])
async def list_tickets(
    status: str = "open", session: AsyncSession = Depends(get_session)
):
    result = await session.execute(select(Ticket).where(Ticket.status == status))
    return result.scalars().all()


@router.post("/tickets", response_model=TicketOut)
async def create_ticket(body: TicketCreate, session: AsyncSession = Depends(get_session)):
    ticket = Ticket(
        title=body.title,
        description=body.description,
        priority=body.priority,
        tags=body.tags,
        context=body.context,
        created_by="api",
    )
    session.add(ticket)
    await session.commit()
    await session.refresh(ticket)
    return ticket


# --- Chat endpoint (send message to a persona) ---

class ChatRequest(BaseModel):
    persona_id: str
    message: str


class ChatResponse(BaseModel):
    response: str


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, session: AsyncSession = Depends(get_session)):
    persona = await session.get(Persona, body.persona_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")

    result = await run_persona(persona, body.message)
    return ChatResponse(response=result)
```

**Step 2: Mount routes in main.py**

Add to `main.py` after app creation:

```python
from opencompany.gateway.api import router as api_router
from opencompany.company.scheduler import register_observers, start_scheduler

app.include_router(api_router, prefix="/api")

# In lifespan, after table creation:
await register_observers()
start_scheduler()
```

**Step 3: Verify API works**

Run: `cd opencompany && uv run opencompany`
Then: `curl http://localhost:8000/api/personas`
Expected: `[]` (empty list, no personas seeded yet)

**Step 4: Commit**

```bash
git add src/opencompany/gateway/ src/opencompany/main.py
git commit -m "feat: REST API for personas, tickets, and chat"
```

---

## Task 11: Seed Company (Initial Org Chart)

**Files:**
- Create: `opencompany/config/company.yaml`
- Create: `opencompany/src/opencompany/company/seed.py`
- Modify: `opencompany/src/opencompany/main.py` — run seed on startup

**Step 1: Create company.yaml**

```yaml
personas:
  - id: ceo
    name: "Morgan Reeves"
    role: "CEO"
    type: manager
    skills: [strategy, delegation, hiring]
    tools: [list_tickets, list_team, hire_persona, fire_persona]
    backstory: >
      Visionary CEO who runs a tight ship. Delegates effectively,
      monitors team performance, and hires when capacity is needed.

  - id: security-analyst
    name: "Sarah Chen"
    role: "Security Analyst"
    type: observer
    reports_to: ceo
    skills: [security, code-review, compliance]
    tools: [read_file, grep_code, list_files, create_ticket]
    watches:
      - source: git_repo
        path: "/src/**"
        schedule: "every 6h"
    backstory: >
      Senior security engineer with 10 years experience.
      Meticulous scanner who catches vulnerabilities others miss.

  - id: security-engineer
    name: "Alex Rivera"
    role: "Security Engineer"
    type: solver
    reports_to: ceo
    skills: [security, python, backend]
    picks_up: [security]
    tools: [read_file, grep_code, list_files, list_tickets, update_ticket]
    backstory: >
      Hands-on security engineer who fixes what the analyst finds.
      Fast, pragmatic, writes clean patches.

  - id: general-solver
    name: "Jamie Park"
    role: "General Engineer"
    type: solver
    reports_to: ceo
    skills: [python, backend, devops, general]
    picks_up: [backend, devops, general]
    tools: [read_file, grep_code, list_files, list_tickets, update_ticket]
    backstory: >
      Versatile engineer who picks up anything that needs doing.
      Reliable, thorough, and fast.

bindings:
  - persona_id: ceo
    match:
      channel: telegram
      chat_type: direct
  - persona_id: ceo
```

**Step 2: Create seed.py**

```python
# src/opencompany/company/seed.py
import logging
import os

import yaml
from sqlalchemy import select

from opencompany.models.db import Persona
from opencompany.models.engine import async_session

logger = logging.getLogger(__name__)


async def seed_company(config_path: str = "config/company.yaml"):
    """Load initial personas from company.yaml if DB is empty."""
    if not os.path.isfile(config_path):
        logger.warning(f"No config at {config_path}, skipping seed")
        return

    async with async_session() as session:
        result = await session.execute(select(Persona).limit(1))
        if result.scalars().first():
            logger.info("Personas already exist, skipping seed")
            return

    with open(config_path) as f:
        config = yaml.safe_load(f)

    async with async_session() as session:
        for p in config.get("personas", []):
            persona = Persona(
                id=p["id"],
                name=p["name"],
                role=p["role"],
                type=p["type"],
                reports_to=p.get("reports_to"),
                skills=p.get("skills", []),
                watches=p.get("watches", []),
                picks_up=p.get("picks_up", []),
                tools=p.get("tools", []),
                backstory=p.get("backstory", ""),
            )
            session.add(persona)
            os.makedirs(os.path.join("workspaces", p["id"]), exist_ok=True)
            logger.info(f"Seeded persona: {p['name']} ({p['id']})")

        await session.commit()

    logger.info(f"Seeded {len(config.get('personas', []))} personas")
```

**Step 3: Add seed to main.py lifespan**

In the lifespan function, after table creation:

```python
from opencompany.company.seed import seed_company
await seed_company()
```

**Step 4: Verify**

Run: `cd opencompany && uv run opencompany`
Then: `curl http://localhost:8000/api/personas | python -m json.tool`
Expected: 4 personas (CEO, Security Analyst, Security Engineer, General Solver)

**Step 5: Commit**

```bash
git add config/company.yaml src/opencompany/company/seed.py src/opencompany/main.py
git commit -m "feat: seed company from company.yaml on first startup"
```

---

## Task 12: Telegram Channel Adapter

**Files:**
- Create: `opencompany/src/opencompany/gateway/channels/__init__.py`
- Create: `opencompany/src/opencompany/gateway/channels/telegram.py`
- Modify: `opencompany/src/opencompany/main.py` — start bot in lifespan

**Step 1: Create telegram.py**

```python
# src/opencompany/gateway/channels/telegram.py
import logging
import os

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from opencompany.agents.runner import run_persona
from opencompany.models.db import Persona
from opencompany.models.engine import async_session

logger = logging.getLogger(__name__)


async def _resolve_persona(channel: str, chat_type: str, peer: str) -> Persona | None:
    """Resolve which persona handles this message based on bindings."""
    # For now: load from company.yaml bindings via DB
    # Default to CEO for direct messages
    async with async_session() as session:
        persona = await session.get(Persona, "ceo")
        return persona


async def _handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to OpenCompany. I'm the team. Ask me anything!"
    )


async def _handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    chat_type = "group" if update.effective_chat.type in ("group", "supergroup") else "direct"
    peer = str(update.effective_user.id)

    persona = await _resolve_persona("telegram", chat_type, peer)
    if not persona:
        await update.message.reply_text("No persona available.")
        return

    await update.message.reply_text(f"[{persona.name}] Processing...")

    try:
        result = await run_persona(persona, user_message)
        # Telegram has a 4096 char limit
        for i in range(0, len(result), 4000):
            await update.message.reply_text(result[i : i + 4000])
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text(f"Error: {str(e)[:200]}")


def create_telegram_app() -> Application | None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN not set, skipping Telegram")
        return None

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", _handle_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_message))
    return app
```

**Step 2: Start bot in main.py lifespan**

```python
from opencompany.gateway.channels.telegram import create_telegram_app

# In lifespan yield block:
telegram_app = create_telegram_app()
if telegram_app:
    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling()
    logger.info("Telegram bot started")

yield

# Shutdown:
if telegram_app:
    await telegram_app.updater.stop()
    await telegram_app.stop()
    await telegram_app.shutdown()
```

**Step 3: Commit**

```bash
git add src/opencompany/gateway/channels/ src/opencompany/main.py
git commit -m "feat: Telegram channel adapter with persona routing"
```

---

## Task 13: Wire Everything Together (Final main.py)

**Files:**
- Modify: `opencompany/src/opencompany/main.py` — complete lifespan with all components

**Step 1: Write final main.py**

```python
# src/opencompany/main.py
import logging
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI

from opencompany.models.base import Base
from opencompany.models.engine import engine
import opencompany.models.db  # noqa: F401

from opencompany.gateway.api import router as api_router
from opencompany.company.seed import seed_company
from opencompany.company.scheduler import register_observers, start_scheduler
from opencompany.gateway.channels.telegram import create_telegram_app
from opencompany.agents.tools import ALL_TOOLS
from opencompany.agents.runner import register_tool

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Register all tools
    for name, func in ALL_TOOLS.items():
        register_tool(name, func)
    logger.info(f"Registered {len(ALL_TOOLS)} tools")

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ready")

    # Seed personas
    await seed_company()

    # Start scheduler for observers
    await register_observers()
    start_scheduler()
    logger.info("Scheduler started")

    # Start Telegram bot
    telegram_app = create_telegram_app()
    if telegram_app:
        await telegram_app.initialize()
        await telegram_app.start()
        await telegram_app.updater.start_polling()
        logger.info("Telegram bot started")

    yield

    # Shutdown
    if telegram_app:
        await telegram_app.updater.stop()
        await telegram_app.stop()
        await telegram_app.shutdown()

    await engine.dispose()


app = FastAPI(title="OpenCompany", version="0.1.0", lifespan=lifespan)
app.include_router(api_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}


def main():
    uvicorn.run("opencompany.main:app", host="0.0.0.0", port=8000, reload=True)
```

**Step 2: End-to-end smoke test**

Run: `docker compose up db redis -d && cd opencompany && uv run opencompany`

Verify:
- `curl http://localhost:8000/health` -> `{"status": "ok"}`
- `curl http://localhost:8000/api/personas` -> 4 personas
- `curl http://localhost:8000/api/tickets` -> `[]`
- `curl -X POST http://localhost:8000/api/tickets -H 'Content-Type: application/json' -d '{"title":"Test ticket","priority":"low","tags":["test"]}'` -> ticket created
- `curl -X POST http://localhost:8000/api/chat -H 'Content-Type: application/json' -d '{"persona_id":"ceo","message":"List the team"}'` -> CEO responds with team list

**Step 3: Commit**

```bash
git add src/opencompany/main.py
git commit -m "feat: wire all components — gateway, scheduler, telegram, tools"
```

---

## Task 14: Auto-Assignment (Event-Driven Solver Dispatch)

**Files:**
- Create: `opencompany/src/opencompany/company/engine.py`

**Step 1: Create engine.py**

```python
# src/opencompany/company/engine.py
"""Company engine: listens for events and orchestrates responses."""
import logging

from sqlalchemy import select, func

from opencompany.agents.runner import run_persona
from opencompany.company.taskboard import find_best_solver
from opencompany.events.bus import publish, subscribe
from opencompany.models.db import Persona, Ticket
from opencompany.models.engine import async_session

logger = logging.getLogger(__name__)


async def _get_solvers_with_workload() -> list[dict]:
    """Get active solvers with their current ticket count."""
    async with async_session() as session:
        q = select(Persona).where(Persona.type == "solver", Persona.status == "active")
        result = await session.execute(q)
        solvers = result.scalars().all()

        solver_list = []
        for s in solvers:
            wq = select(func.count(Ticket.id)).where(
                Ticket.assigned_to == s.id,
                Ticket.status.in_(["assigned", "in_progress"]),
            )
            wresult = await session.execute(wq)
            workload = wresult.scalar() or 0
            solver_list.append({
                "id": s.id,
                "skills": s.skills,
                "picks_up": s.picks_up,
                "workload": workload,
            })

        return solver_list


async def handle_event(event_type: str, data: dict):
    """Handle events from the bus."""
    if event_type == "ticket.created":
        await _auto_assign_ticket(data["ticket_id"])
    elif event_type == "ticket.review":
        await _trigger_review(data["ticket_id"])


async def _auto_assign_ticket(ticket_id: int):
    """Auto-assign a ticket to the best available solver."""
    async with async_session() as session:
        ticket = await session.get(Ticket, ticket_id)
        if not ticket or ticket.status != "open":
            return

        solvers = await _get_solvers_with_workload()
        # Use picks_up tags for matching, fall back to skills
        for solver in solvers:
            solver["skills"] = solver["picks_up"] or solver["skills"]

        best = find_best_solver(tags=ticket.tags, solvers=solvers)
        if not best:
            logger.warning(f"No solver found for ticket #{ticket_id} tags={ticket.tags}")
            return

        ticket.assigned_to = best["id"]
        ticket.status = "assigned"
        await session.commit()
        logger.info(f"Assigned ticket #{ticket_id} to {best['id']}")

        # Trigger the solver to work on it
        persona = await session.get(Persona, best["id"])

    if persona:
        task = f"""You have been assigned ticket #{ticket.id}: {ticket.title}

Description: {ticket.description}
Priority: {ticket.priority}
Context: {ticket.context}

Investigate and solve this issue. When done, call update_ticket with the result and set status to 'review'."""

        await run_persona(persona, task)


async def _trigger_review(ticket_id: int):
    """Trigger reviewer for a completed ticket."""
    async with async_session() as session:
        ticket = await session.get(Ticket, ticket_id)
        if not ticket:
            return

        # Find the original creator (observer) to review
        reviewer = await session.get(Persona, ticket.created_by)
        if not reviewer:
            # Fall back to any manager
            q = select(Persona).where(Persona.type == "manager", Persona.status == "active")
            result = await session.execute(q)
            reviewer = result.scalars().first()

    if reviewer:
        task = f"""Review ticket #{ticket.id}: {ticket.title}

Solution: {ticket.result}

If the solution is good, call update_ticket with status='done'.
If not, call update_ticket with status='rejected' and explain what's wrong."""

        await run_persona(reviewer, task)


async def start_event_listener():
    """Start listening for events from the bus."""
    logger.info("Company engine event listener started")
    await subscribe(handle_event)
```

**Step 2: Start event listener in main.py lifespan**

```python
import asyncio
from opencompany.company.engine import start_event_listener

# In lifespan, after scheduler start:
asyncio.create_task(start_event_listener())
```

**Step 3: Commit**

```bash
git add src/opencompany/company/engine.py src/opencompany/main.py
git commit -m "feat: company engine — auto-assignment and solver dispatch via events"
```

---

## Summary

| Task | What it builds | Key files |
|------|---------------|-----------|
| 1 | Project scaffold | pyproject.toml, main.py |
| 2 | Docker (Postgres + Redis) | docker-compose.yml, Dockerfile |
| 3 | DB models | models/db.py |
| 4 | DB connection + migrations | models/engine.py, alembic |
| 5 | Agent runner (Strands + LiteLLM) | agents/runner.py, prompts.py |
| 6 | Core tools (tickets, code, company) | agents/tools/*.py |
| 7 | Company engine — personas & task board | company/personas.py, taskboard.py |
| 8 | Event bus (Redis pub/sub) | events/bus.py |
| 9 | Scheduler (observer triggers) | company/scheduler.py |
| 10 | Gateway REST API | gateway/api.py |
| 11 | Seed company (company.yaml) | config/company.yaml, company/seed.py |
| 12 | Telegram adapter | gateway/channels/telegram.py |
| 13 | Wire everything together | main.py final |
| 14 | Auto-assignment + solver dispatch | company/engine.py |

After these 14 tasks you'll have a working system where:
- 4 personas are seeded from YAML
- Security Analyst scans code every 6h, creates tickets
- Tickets auto-assign to matching solvers
- Solvers work tickets and submit for review
- CEO can hire/fire via chat
- REST API exposes everything
- Telegram bot routes to personas
- All backed by Postgres + Redis in Docker
