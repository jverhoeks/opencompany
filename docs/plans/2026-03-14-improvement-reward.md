# OpenCompany — Improvement Plan

> Based on reading the repo structure, README, architecture diagram, and source layout in `src/opencompany/`.  
> Improvements are ordered by impact vs. effort, not by module.

---

## Diagnosed Problems

### 1. Push assignment creates idle pileup
`taskboard.py` skill-matches and *pushes* a ticket to a persona. If that persona is busy or slow, the ticket waits — even if five other personas are available and partially qualified. There is no pull fallback.

**Symptom:** "too many workers waiting" — they're waiting for the scheduler sweep to re-assign, not waiting for work to become available.

### 2. Periodic scheduler sweep = latency gaps and wasted cycles
`scheduler.py` runs sweeps on `CEO_KICKOFF_INTERVAL_SECONDS` and `HEARTBEAT_INTERVAL_SECONDS`. Both default to `0` (off). When on, they fire regardless of whether anything changed. A persona finishing a task doesn't trigger the next assignment — it waits for the next sweep tick.

**Symptom:** Idle personas sitting between ticks even when open tickets exist.

### 3. No per-task token budget — only per-persona daily caps
`budget.py` enforces a daily token limit per persona, but there is no per-task cap. A single complex task (e.g. "build the entire landing page") can burn most of a persona's daily budget before the scheduler can reassign simpler tasks to other workers.

**Symptom:** "one in bus mode that does all" — one persona with the right skill set gets a large ticket and exhausts their budget doing it end-to-end.

### 4. HR hiring is uncapped relative to available work
HR (`hire_persona`) autonomously hires up to 15+ personas for tasks. There is no check on current queue depth vs. active worker count before hiring. The result is a large pool of personas competing for sparse tickets, most of them idle.

**Symptom:** 15 personas hired, 3 tickets in the queue.

### 5. No work-stealing from blocked personas
When a persona calls `contact_overseer`, their in-progress ticket doesn't get redistributed. Tickets can sit "assigned" while the persona waits indefinitely for human input.

**Symptom:** Tickets stuck in `in_progress` with no active worker.

### 6. No efficiency metrics — you can't see where tokens go
`budget.py` tracks budget consumed per persona, but there's no breakout of tokens per task, tokens per role, idle time, or throughput (tasks completed / tokens spent). Without this you can't tune.

**Symptom:** No answer to "which persona is the most expensive per unit of work produced?"

### 7. System prompts are hardcoded in `prompts.py`
Persona personality and role instructions are built in Python code. Changing how a persona behaves requires a code change + restart, not an edit to a config file.

**Symptom:** Slow iteration on org behaviour.

---

## Improvement Plan

### P0 — Fix the scheduler: event-driven assignment

**Problem:** Sweep-based scheduler creates unnecessary latency.  
**Fix:** Emit a Redis event on every status transition. The scheduler subscribes and re-runs assignment only when something actually changes.

```python
# events/bus.py — add these event types
class EventType(str, Enum):
    TICKET_CREATED    = "ticket.created"
    TICKET_COMPLETED  = "ticket.completed"
    PERSONA_IDLE      = "persona.idle"       # <-- new
    PERSONA_BLOCKED   = "persona.blocked"    # <-- new

# company/scheduler.py — replace interval sweep with reactive handler
async def on_persona_idle(event: Event):
    """Triggered when a persona finishes a task. Immediately try to assign next."""
    persona_id = event.payload["persona_id"]
    await taskboard.assign_next(persona_id)   # pull next best-match ticket

async def on_ticket_created(event: Event):
    """Triggered when a new ticket appears. Find best idle persona immediately."""
    await taskboard.try_assign(event.payload["ticket_id"])
```

**Impact:** Eliminates idle gaps between sweep ticks. Assignment latency drops from `SWEEP_INTERVAL` seconds to milliseconds.

---

### P1 — Add per-task token budget alongside daily persona budget

**Problem:** No guard against one large task burning a persona's daily budget.  
**Fix:** Add `budget_tokens` to the ticket model. `runner.py` enforces it. If the task exceeds budget, it returns a partial result and re-queues.

```python
# models/db.py
class Ticket(Base):
    ...
    budget_tokens: int = 4000   # per-task cap (new field)
    tokens_used:   int = 0      # tracked post-run

# agents/runner.py — add budget guard
max_output = min(
    ticket.budget_tokens - input_tokens,
    persona.remaining_daily_budget,
    2000   # hard output ceiling
)
if max_output < 200:
    # Can't do meaningful work — re-queue for later
    await taskboard.requeue(ticket.id, reason="budget_exhausted")
    return
```

**Migration:** Add column `budget_tokens INT DEFAULT 4000` and `tokens_used INT DEFAULT 0` to tickets table.

---

### P2 — Pull-based claiming as fallback to push assignment

**Problem:** Pushed assignment + busy persona = idle ticket.  
**Fix:** Keep skill-match push as primary. Add a pull endpoint and a heartbeat that lets idle personas claim unassigned work.

```python
# company/taskboard.py — add claim_next()
async def claim_next(persona_id: str, session: AsyncSession) -> Ticket | None:
    """
    Atomic: finds the best open ticket for this persona and claims it.
    Used as fallback when push assignment missed the persona (e.g. was busy).
    """
    persona = await get_persona(persona_id, session)
    candidates = await session.execute(
        select(Ticket)
        .where(Ticket.status == "open")
        .where(Ticket.required_skills.overlap(persona.skills))   # PG array overlap
        .order_by(Ticket.priority.desc(), Ticket.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)   # atomic — skip if another tx has it
    )
    ticket = candidates.scalar_one_or_none()
    if ticket:
        ticket.status = "assigned"
        ticket.assignee_id = persona_id
        await session.commit()
    return ticket
```

The `PERSONA_IDLE` event triggers `claim_next` automatically. No polling needed.

---

### P3 — Capacity-aware hiring

**Problem:** HR hires freely regardless of queue depth.  
**Fix:** Expose a `capacity_ratio()` function; gate `hire_persona` on it.

```python
# company/personas.py
async def capacity_ratio(session: AsyncSession) -> float:
    """open_tickets / active_solvers. >2.0 means understaffed."""
    open_count   = await count_tickets(status="open", session=session)
    solver_count = await count_active_personas(trust__gte="solver", session=session)
    return open_count / max(solver_count, 1)

# agents/tools/hire_persona.py — wrap the existing tool
@tool
async def hire_persona(name: str, role: str, skills: list[str], ...):
    ratio = await capacity_ratio(session)
    if ratio < 1.5:
        return "Hiring rejected: team has sufficient capacity (ratio={:.1f}). No hire needed.".format(ratio)
    # ... existing hire logic
```

Add a `MAX_TEAM_SIZE` config cap (e.g. 12) as a hard ceiling regardless of ratio.

---

### P4 — Work-stealing from blocked personas

**Problem:** Tickets stuck `in_progress` when persona is waiting for overseer.  
**Fix:** A lightweight stale-claim sweeper — much cheaper than the full scheduler sweep.

```python
# company/scheduler.py — small targeted job, run every 2 minutes
async def expire_stale_assignments():
    cutoff = datetime.utcnow() - timedelta(minutes=10)
    stale = await session.execute(
        select(Ticket)
        .where(Ticket.status == "in_progress")
        .where(Ticket.updated_at < cutoff)
    )
    for ticket in stale.scalars():
        ticket.status = "open"
        ticket.assignee_id = None
        await bus.publish(EventType.TICKET_CREATED, {"ticket_id": ticket.id})
```

Personas waiting for overseer should move their ticket to a `waiting_overseer` status so it doesn't get stolen, but they themselves become available for other work.

---

### P5 — Efficiency metrics dashboard panel

**Problem:** No visibility into tokens/task, idle time, throughput.  
**Fix:** Populate a `work_logs` table on every task completion and expose a metrics endpoint.

```python
# models/db.py — WorkLog already exists, ensure these fields are tracked:
class WorkLog(Base):
    persona_id:   str
    ticket_id:    str
    tokens_in:    int
    tokens_out:   int
    duration_sec: float
    outcome:      str   # "done" | "blocked" | "requeued" | "failed"
    created_at:   datetime

# gateway/api.py — new endpoint
@router.get("/api/metrics/efficiency")
async def efficiency_metrics(session=Depends(get_session)):
    return await session.execute("""
        SELECT
            p.name,
            p.role,
            COUNT(w.id)                          AS tasks_completed,
            SUM(w.tokens_in + w.tokens_out)      AS total_tokens,
            AVG(w.duration_sec)                  AS avg_duration_sec,
            SUM(w.tokens_in + w.tokens_out)
              / NULLIF(COUNT(w.id), 0)            AS tokens_per_task
        FROM work_logs w
        JOIN personas p ON p.id = w.persona_id
        WHERE w.outcome = 'done'
        GROUP BY p.name, p.role
        ORDER BY tokens_per_task DESC
    """)
```

Add a **Metrics** tab to the Control Tower dashboard rendering this as a sortable table. Highlight outliers (high tokens/task = prompt tuning needed).

---

### P6 — DB-backed persona config with live editor + YAML as template

**Problem:** Persona instructions are in code (slow to iterate) and YAML (requires restart to take effect mid-run).  
**Decision:** YAML is the *org template* format (Git-versioned, bootstraps from `company-novacraft.yaml` etc.). DB is the *live working state* once a company is running. A persona editor in the Control Tower edits the DB directly — no restart needed.

#### Lifecycle

```
startup
  └─ no active company in DB?
       └─ seed_from_yaml(company.yaml) → write all personas/roles to DB
  └─ active company exists?
       └─ load from DB (YAML ignored)

while running
  └─ every 5 minutes → snapshot_to_db()     # log / audit trail
  └─ on all tasks done → snapshot_to_db()   # final state capture

manual
  └─ POST /api/config/export → dump DB state back to YAML file
```

#### Migration strategy

`PersonaConfig` and `CompanySnapshot` are **new tables alongside the existing `Persona` model** — not a replacement. `Persona` stays as the runtime identity record (status, current ticket, active flag). `PersonaConfig` is the editable behaviour layer. This keeps the migration non-destructive and rollback-safe.

```bash
# New Alembic migration
uv run alembic revision --autogenerate -m "add_persona_config_and_snapshots"
uv run alembic upgrade head
```

The migration only adds tables — nothing is dropped or altered. Safe to run against an existing DB with live data.

#### DB schema additions

```python
# models/db.py

class PersonaConfig(Base):
    """Live editable config for a persona. Loaded by prompts.py at each run."""
    __tablename__ = "persona_configs"

    id:               str       # FK → personas.id
    name:             str
    role:             str
    trust:            str
    skills:           list[str]  # PG array
    budget_tokens_daily: int
    instructions:     str       # the editable role behaviour block
    personality:      dict      # JSON: traits, quirks, catchphrases
    updated_at:       datetime
    updated_by:       str       # "system" | "overseer" | persona_id (self-edit)

class CompanySnapshot(Base):
    """Append-only log. Written every 5 min + on completion."""
    __tablename__ = "company_snapshots"

    id:           int           # autoincrement
    trigger:      str           # "interval" | "tasks_complete" | "manual"
    snapshot:     dict          # full JSON dump of all PersonaConfigs + ticket stats
    created_at:   datetime
```

#### Startup seeding

```python
# company/config.py

async def boot(session: AsyncSession, yaml_path: Path):
    """
    Seed DB from YAML on first boot; skip if company already active.
    """
    existing = await session.scalar(select(func.count(PersonaConfig.id)))
    if existing > 0:
        logger.info("Company already in DB — skipping YAML seed")
        return

    cfg = yaml.safe_load(yaml_path.read_text())
    for pid, pdata in cfg["personas"].items():
        session.add(PersonaConfig(
            id=pid,
            updated_by="system",
            updated_at=datetime.utcnow(),
            **pdata
        ))
    await session.commit()
    logger.info(f"Seeded {len(cfg['personas'])} personas from {yaml_path.name}")
```

#### Snapshot job (replaces / extends existing scheduler)

```python
# company/scheduler.py

async def snapshot_company(trigger: str, session: AsyncSession):
    configs   = (await session.execute(select(PersonaConfig))).scalars().all()
    stats     = await get_ticket_stats(session)
    snapshot  = {
        "personas": [c.__dict__ for c in configs],
        "tickets":  stats,
    }
    session.add(CompanySnapshot(trigger=trigger, snapshot=snapshot,
                                created_at=datetime.utcnow()))
    await session.commit()
    logger.info(f"Snapshot saved [{trigger}]")

# Add to APScheduler setup:
scheduler.add_job(
    lambda: asyncio.create_task(snapshot_company("interval", session)),
    "interval", minutes=5, id="snapshot_interval"
)

# Call from task completion handler:
async def on_all_tasks_complete():
    await snapshot_company("tasks_complete", session)
    await bus.publish(EventType.COMPANY_IDLE, {})
```

#### `prompts.py` change

```python
# agents/prompts.py — read instructions from DB, not hardcoded

async def build_system_prompt(persona_id: str, session: AsyncSession) -> str:
    cfg = await session.get(PersonaConfig, persona_id)
    return PROMPT_TEMPLATE.format(
        name=cfg.name,
        role=cfg.role,
        instructions=cfg.instructions,
        personality=json.dumps(cfg.personality),
        trust=cfg.trust,
        skills=", ".join(cfg.skills),
    )
```

#### Export back to YAML

```python
# gateway/api.py

@router.post("/api/config/export")
async def export_to_yaml(session=Depends(get_session)):
    """Dump current DB state back to a versioned YAML template."""
    configs = (await session.execute(select(PersonaConfig))).scalars().all()
    data = {"personas": {c.id: {
        "name": c.name, "role": c.role, "trust": c.trust,
        "skills": c.skills, "budget_tokens_daily": c.budget_tokens_daily,
        "instructions": c.instructions, "personality": c.personality,
    } for c in configs}}
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M")
    out = Path(f"config/company-export-{ts}.yaml")
    out.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False))
    return {"exported_to": str(out)}
```

#### Persona editor in Control Tower

New **Config** tab in the dashboard. Key design decisions:
- **Free-edit fields** (safe mid-run): `instructions`, `budget_tokens_daily`, `personality`, `skills`
- **Locked fields** (require company pause): `trust`, `role`, org relationships
- Changes write to `PersonaConfig` immediately and set `updated_by = "overseer"`
- The next time that persona starts a task, it picks up the new instructions automatically
- A **Snapshot History** panel shows the 10 most recent `CompanySnapshot` rows with diffs

```
┌─────────────────────────────────────────────────────────┐
│  Config  │  Team  │  Tasks  │  Activity  │  Metrics     │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌───────────────────────────────┐   │
│  │ Morgan Hayes │  │ Instructions            [Save] │   │
│  │ (CEO)        │  │ ┌─────────────────────────┐   │   │
│  │ ──────────   │  │ │ You are Morgan Hayes...  │   │   │
│  │ Quinn N.     │  │ │ [editable textarea]      │   │   │
│  │ (HR)         │  │ └─────────────────────────┘   │   │
│  │ ──────────   │  │                               │   │
│  │ Taylor Kim   │  │ Daily token budget:  [50000]  │   │
│  │ (CTO)        │  │ Skills: planning, delegation  │   │
│  └──────────────┘  └───────────────────────────────┘   │
│                                                         │
│  Snapshots: ● 14:35 interval  ● 14:30 interval          │
│             ● 14:12 tasks_complete  [export to YAML]    │
└─────────────────────────────────────────────────────────┘
```

---

### P7 — Per-role concurrency limit

**Problem:** No cap on how many tickets one persona runs simultaneously (currently 1 at a time, but nothing prevents a future change from spawning many concurrent `runner.py` calls per persona).  
**Fix:** Simple semaphore per persona in `runner.py`.

```python
# agents/runner.py
_persona_locks: dict[str, asyncio.Semaphore] = {}

def get_lock(persona_id: str, max_concurrent: int = 1) -> asyncio.Semaphore:
    if persona_id not in _persona_locks:
        _persona_locks[persona_id] = asyncio.Semaphore(max_concurrent)
    return _persona_locks[persona_id]

async def run_task(persona, ticket, ...):
    async with get_lock(persona.id):
        ...  # existing execution logic
```

`max_concurrent` can be set per-role in YAML (leads/solvers = 1, CEO = 2 to handle delegation while also tracking progress).

---

---

## Research & Marketing Roles

Two new personas added to `company-novacraft.yaml` (and `company-musk.yaml`). They work like any other persona — claim tickets, use tools — but are triggered proactively by the scheduler at project start.

**Researcher (`alex-chen`, solver trust)**
- Runs at project kickoff, before any design or code tickets are assigned
- Uses `web_search` + `web_fetch` to map the domain: competitors, tech choices, user needs
- Saves findings to `workspace/research/{topic}.md`
- The `create_ticket` tool in other personas' prompts is instructed to check for a research doc first
- Success metric: research doc exists and is linked in at least one ticket before dev starts

**Marketer (`jordan-lee`, solver trust)**
- Triggered when tickets with `marketing` or `copy` tags appear
- Reads researcher findings before writing anything
- Copy is always assigned a review ticket before the marketer marks done
- No access to `hire_persona` or `run_script` — pure content role

Both are capacity-aware: if the project is purely internal/technical, neither is hired. The capacity ratio check in P3 is extended to check `required_skills` overlap before spawning either role.

---

## Self-Improvement Loop (soul.md)

This is the autoresearch `program.md` insight applied to company behaviour. Instead of humans editing `company.yaml` to change how personas act, the company reads its own performance data and proposes targeted updates to `soul.md` — its living operating principles.

### How it works

```
project completes
    └─ snapshot_company("tasks_complete")      # capture final state
    └─ run_reflexion()                         # Company Analyst runs
           ├─ read soul.md (current rules)
           ├─ read WorkLog metrics (tokens/task, completion rate by role)
           ├─ read latest CompanySnapshot
           └─ propose updated soul.md
                  ├─ passes validation gates?
                  │       ├─ version incremented?
                  │       ├─ ≤ 3 rule changes?
                  │       ├─ protected rules intact?
                  │       └─ ≤ 200 lines?
                  ├─ YES → apply, persist to soul_versions, publish SOUL_UPDATED
                  └─ NO  → log rejection reason, keep current soul.md
```

The loop is **Reflexion pattern**: an agent generates initial output, receives feedback from a judge agent, and then refines its work based on that feedback — mimicking human creative processes where initial drafts are refined through critique and revision. Here the "judge" is the validation gate in `SoulManager`, and the metric being optimised is `tokens_per_completed_task` — the company's equivalent of autoresearch's `val_bpb`.

### New files

| File | Purpose |
|---|---|
| `soul.md` | Living operating principles. Read by every persona at task start via system prompt injection |
| `company/soul.py` | `SoulManager`: read, version, validate, apply, rollback |
| `company/reflexion.py` | Company Analyst agent — runs on project completion, proposes soul.md patches |
| `agents/tools/update_soul.py` | `propose_soul_update` tool — lead+ personas can also propose soul changes directly |
| `models/db.py` | New `SoulVersion` table — append-only log of every accepted soul.md version |

### New DB table

```python
class SoulVersion(Base):
    __tablename__ = "soul_versions"
    id:           int       # autoincrement PK
    version:      int       # soul.md version number, unique
    content:      str       # full text at this version
    diff:         str       # unified diff from previous
    rationale:    str       # why this change was proposed
    proposed_by:  str       # "company-analyst" | "overseer" | persona_id
    created_at:   datetime
```

### soul.md injection into every persona

`prompts.py` reads `soul.md` at task start and injects it into every persona's system prompt. This means a soul update takes effect on the **next task** — no restart, no re-seeding the DB.

```python
# agents/prompts.py
soul_content = Path("soul.md").read_text()
return PROMPT_TEMPLATE.format(..., soul=soul_content)
```

### Validation gates (in `SoulManager.propose_update`)

These prevent the self-improvement loop from going rogue:

1. **Version must be incremented** — prevents identical re-submissions
2. **≤ 3 rule changes** (`MAX_RULES_PER_UPDATE`) — prevents wholesale rewrites
3. **Protected rules intact** — "No hardcoded secrets", "overseer approval", "Self-Improvement Rules" cannot be removed
4. **≤ 200 lines** — keeps soul.md focused; role-specific detail belongs in SOP files

### Personas can also propose soul changes

The `propose_soul_update` tool is available to `lead` trust tier and above. A persona who notices a pattern — e.g. the CEO noticing all CRITICAL tickets take 3x longer than estimated — can propose a rule change directly. It goes through the same validation gates as the analyst.

### Dashboard: Soul History panel

A new **Soul** tab in the Control Tower shows:
- Current `soul.md` rendered as markdown
- Diff view for each version in `soul_versions`
- Rollback button (calls `SoulManager.rollback(version)`)
- Pending proposals waiting for overseer approval (if a protected rule change is requested)

---

## Strands SDK Features to Adopt

These are native Strands capabilities you're not using yet, ordered by impact on OpenCompany specifically.

---

### S1 — Sub-agents via Agent-as-Tool (your "subagent" question)

**Yes, this is a good idea — but scope it carefully.**

Strands 1.0 multi-agent patterns are designed to be gradually adopted and freely combined — start with single agents, add specialists as tools, evolve to swarms, and orchestrate with graphs as your needs grow.

The right pattern for OpenCompany is **Agent-as-Tool**, not a full Swarm. A developer persona working on "Build the landing page" can spawn a sub-agent for a parallelisable sub-task — e.g. writing the CSS while the parent continues on the HTML. The parent controls the sub-agent as a tool call, collects the result, and continues. It's fast, scoped, and the token cost is visible and bounded.

```python
# agents/tools/spawn_subagent.py

from strands import Agent, tool
from strands.models.bedrock import BedrockModel

@tool
async def spawn_subagent(
    task: str,
    role: str = "solver",
    budget_tokens: int = 2000
) -> str:
    """
    Spin up a short-lived sub-agent to handle a parallelisable sub-task.
    Only available to solver trust tier and above.
    Returns the sub-agent's result as a string.
    """
    sub = Agent(
        model=BedrockModel(model_id="us.anthropic.claude-sonnet-4-20250514-v1:0"),
        system_prompt=f"You are a specialist {role}. Complete the task concisely. "
                      f"Token budget: {budget_tokens}. Return only your result.",
        tools=[read_file, write_file, grep_code],   # subset of parent's tools
        max_tokens=budget_tokens,
    )
    result = await sub.invoke_async(task)
    return str(result)
```

The parent persona calls `spawn_subagent("Write CSS for ByteSlice landing page, dark theme")` and gets back the CSS. The sub-agent has no access to hire/fire, create tickets, or contact overseer — only file tools. This is the trust tier model applied to sub-agents.

**Guardrails:** Cap at 2 concurrent sub-agents per persona (via semaphore). Sub-agents can't spawn further sub-agents (no recursion). Token cost is attributed to the parent persona's daily budget.

The **Swarm** pattern (all agents in parallel with shared memory) would also work but is harder to cost-control and harder to debug in the Control Tower. Agent-as-Tool gives you visibility — each sub-agent call shows up as a tool call in the persona's trace.

---

### S2 — Hooks for budget tracking and observability (replaces custom callback_handler)

You're currently using a custom `budget_tracker` callback. Strands hooks provide the perfect interface for adding sophisticated functionality without cluttering your core agent logic — for observability, security and guardrails, and memory and state management.

Replace the callback with proper Hooks. This gives you lifecycle events for free:

```python
# agents/hooks.py
from strands.hooks import HookProvider, AfterInvocationEvent, BeforeToolUseEvent

class CompanyHooks(HookProvider):
    def __init__(self, persona_id: str, ticket_id: str, budget: BudgetTracker):
        self.persona_id = persona_id
        self.ticket_id  = ticket_id
        self.budget     = budget

    def register_hooks(self, registry):
        registry.add_callback(AfterInvocationEvent,  self.on_invocation_complete)
        registry.add_callback(BeforeToolUseEvent,    self.on_tool_use)

    async def on_invocation_complete(self, event):
        tokens = event.usage.total_tokens
        await self.budget.record(self.persona_id, self.ticket_id, tokens)
        await bus.publish(EventType.PERSONA_IDLE, {"persona_id": self.persona_id})

    async def on_tool_use(self, event):
        # Log every tool call to WorkLog for the metrics panel
        await worklog.record_tool(self.persona_id, self.ticket_id, event.tool.name)

# In runner.py:
agent = Agent(
    model=model,
    system_prompt=build_system_prompt(persona),
    tools=get_tools_for_trust(persona),
    hooks=[CompanyHooks(persona.id, ticket.id, budget)]   # replaces callback_handler
)
```

The `AfterInvocationEvent` hook is also the clean place to trigger the P0 event-driven scheduler — when an agent finishes, the hook fires `PERSONA_IDLE` on the Redis bus, which immediately triggers `claim_next`.

---

### S3 — Strands Hooks for Steering (guardrail against runaway hiring)

Steering lets you evaluate agent responses and guide the model to retry with corrective feedback, keeping the agent within the painted lines rather than stopping it cold.

This is better than the P3 capacity ratio check in `hire_persona` because it can intercept *any* problematic output, not just hiring calls:

```python
from strands.hooks import BeforeInvocationEvent

class HiringGuardrail(HookProvider):
    def register_hooks(self, registry):
        registry.add_callback(BeforeToolUseEvent, self.check_hire)

    async def check_hire(self, event):
        if event.tool.name != "hire_persona":
            return
        ratio = await capacity_ratio(session)
        if ratio < 1.5:
            # Steer: inject corrective context instead of hard-blocking
            event.add_message(
                "SYSTEM GUARDRAIL: Current capacity ratio is {:.1f}. "
                "Team is sufficiently staffed. Do NOT hire. "
                "Assign existing team members instead.".format(ratio)
            )
```

---

### S4 — Session Manager for persona memory across runs

You have a custom `memory.py` with `remember`/`recall` tools. Strands 1.0 includes a new session manager for retrieving agent state from a remote datastore, and the system handles concurrent agents within the same session for multi-agent scenarios, ensuring your agents maintain context across deployments, scaling events, and system restarts.

The community has a **Valkey/Redis session manager** — which you already run as a sidecar. Swapping your custom `PersonaMemory` table for the Strands Redis session manager means:

- Persona conversation history survives a container restart automatically
- No custom `remember`/`recall` tool needed — context is injected by the session manager
- Works with the existing Redis sidecar, no new infrastructure

```python
from strands_community.session_managers import RedisSessionManager

session_manager = RedisSessionManager(redis_url=REDIS_URL)

agent = Agent(
    model=model,
    system_prompt=build_system_prompt(persona),
    tools=get_tools_for_trust(persona),
    session_id=f"persona-{persona.id}",         # per-persona session
    session_manager=session_manager,
    hooks=[CompanyHooks(persona.id, ticket.id, budget)]
)
```

---

### S5 — OpenTelemetry tracing (replaces custom WorkLog for observability)

Strands can record agent trajectories — the sequence of steps an agent takes for each request. It uses OpenTelemetry standards to emit this data, meaning you can plug it into any OTEL-compatible monitoring backend such as AWS X-Ray, CloudWatch, and Jaeger to visualize and analyze agent behavior. Each run can produce a trace with spans for each significant action including metadata like the prompt, model parameters, and token usage counts.

On AWS (your CDK deployment), adding OTEL takes one line — wrap the ECS entrypoint with `opentelemetry-instrument`. You get per-persona traces in CloudWatch automatically, with spans for every tool call, LLM call, and token count. This is more powerful than the custom `metrics.py` endpoint and requires zero application code changes.

```dockerfile
# Dockerfile — just wrap the command
CMD ["opentelemetry-instrument", "uvicorn", "opencompany.main:app", "--host", "0.0.0.0"]
```

In the CDK stack, add X-Ray/CloudWatch OTEL permissions to the task role. Now every persona run appears as a trace in the CloudWatch GenAI Observability dashboard with full token attribution.

---

### S6 — Agent SOP (Standard Operating Procedures) for complex multi-step tasks

Strands has an `agent-sop` repo: natural language workflows that enable AI agents to perform complex, multi-step tasks with consistency and reliability.

For known repeatable tasks — "set up a new project", "do a code review", "deploy to staging" — you can define an SOP as a Markdown file. The persona reads the SOP and follows it step by step, making the behaviour deterministic without writing Python workflow code.

```markdown
# sops/code_review.md
## Code Review SOP

1. Read all files in the task's workspace directory
2. Check for: syntax errors, missing error handling, hardcoded secrets
3. Write a `review.md` file with findings grouped by severity (CRITICAL / WARN / INFO)
4. Update the ticket status to "review" 
5. If CRITICAL issues found: reassign to original developer with review.md
6. If no CRITICAL issues: update ticket status to "done"
```

The persona gets `sops/code_review.md` appended to their system prompt when assigned a review ticket. Consistent, auditable, no extra agent infrastructure.

---

### Strands Features Summary

| Feature | Current approach | Strands native alternative | Benefit |
|---|---|---|---|
| Sub-agents | Not implemented | Agent-as-Tool (`spawn_subagent`) | Parallelise work within a ticket |
| Budget/event tracking | Custom `callback_handler` | Hooks (`AfterInvocationEvent`) | Clean lifecycle, triggers P0 scheduler |
| Hiring guardrail | Ratio check in tool | Hooks + Steering | Intercepts any policy violation |
| Persona memory | Custom `PersonaMemory` table + tools | Redis Session Manager | Automatic, survives restarts |
| Observability | Custom `metrics.py` endpoint | OpenTelemetry + CloudWatch | Full traces, zero code change |
| Repeatable tasks | Hardcoded prompts | Agent SOP Markdown files | Deterministic, human-readable |

---

## Summary Table

| Priority | Change | Files affected | Effort |
|---|---|---|---|
| P0 | Event-driven scheduler | `scheduler.py`, `bus.py` | Medium |
| P1 | Per-task token budget | `models/db.py`, `runner.py`, migration | Small |
| P2 | Pull-based claim fallback | `taskboard.py` | Small |
| P3 | Capacity-aware hiring | `personas.py`, `tools/hire_persona.py` | Small |
| P4 | Work-stealing / stale claim expiry | `scheduler.py`, ticket status model | Small |
| P5 | Efficiency metrics endpoint + dashboard panel | `api.py`, `dashboard.html` | Medium |
| P6 | DB-backed persona config + live editor + snapshots | `models/db.py`, `config.py`, `scheduler.py`, `prompts.py`, `api.py`, `dashboard.html` | Large |
| P7 | Per-persona concurrency semaphore | `runner.py` | Tiny |
| R1 | Researcher persona (Alex Chen) | `company-novacraft.yaml`, `company-musk.yaml` | Tiny |
| R2 | Marketer persona (Jordan Lee) | `company-novacraft.yaml` | Tiny |
| SI1 | `soul.md` — living operating principles | new file | Tiny |
| SI2 | `SoulManager` — version, validate, apply | `company/soul.py`, `models/db.py`, migration | Small |
| SI3 | `run_reflexion` — Company Analyst self-improvement loop | `company/reflexion.py`, `scheduler.py` | Medium |
| SI4 | `propose_soul_update` tool for personas | `agents/tools/update_soul.py`, trust config | Small |
| SI5 | Soul history panel in Control Tower | `dashboard.html`, `api.py` | Small |
| S1 | Sub-agents via Agent-as-Tool | `tools/spawn_subagent.py`, `runner.py` | Medium |
| S2 | Strands Hooks (replaces callback_handler) | `agents/hooks.py`, `runner.py` | Small |
| S3 | Steering guardrail for hiring | `agents/hooks.py` | Small |
| S4 | Redis Session Manager (replaces PersonaMemory) | `runner.py`, migration | Medium |
| S5 | OpenTelemetry tracing | `Dockerfile`, CDK stack | Small |
| S6 | Agent SOP files for repeatable tasks | `sops/*.md`, `prompts.py` | Small |

---

## Implementation Session (tomorrow)

### Start here — P6 implementation order

1. **Write the Alembic migration** — add `persona_configs` and `company_snapshots` tables
2. **Add `PersonaConfig` and `CompanySnapshot` ORM models** to `models/db.py`
3. **`company/config.py`** — `boot()` seeding function (YAML → DB on first start)
4. **`company/scheduler.py`** — add `snapshot_company()` + 5-min interval job + hook into the "all tasks done" event
5. **`agents/prompts.py`** — swap hardcoded prompt building for `build_system_prompt()` that reads from DB
6. **`gateway/api.py`** — add `GET /api/config/personas`, `PATCH /api/config/personas/{id}`, `POST /api/config/export`
7. **`dashboard.html`** — add Config tab with persona list, instructions editor, snapshot history panel

Each step is independently testable — you can validate the migration before touching prompts, validate prompts before touching the API, etc.

---

## Suggested Implementation Order

**Sprint 1 — Stop the bleeding (P1, P2, P3, P4)**  
These are all small, contained changes. Together they eliminate the two core failure modes: one worker doing everything, and too many idle workers.

**Sprint 2 — Make it reactive (P0)**  
Replace sweep-based scheduling with event-driven assignment. This is the architectural change with the highest leverage — it makes the system feel alive rather than sluggish.

**Sprint 3 — Make it observable (P5)**  
Without metrics you can't validate that Sprint 1 & 2 worked. Add the efficiency panel so you can actually see tokens/task improving.

**Sprint 4 — Make it programmable (P6, P7)**  
Move persona config to DB with a live editor. YAML stays as the org template format — it seeds the DB on first boot, and you can export back to YAML at any time. The 5-minute snapshot + on-completion snapshot gives you a full audit log of how the org evolved during a run. P7 (concurrency semaphore) is a one-liner on top of this.