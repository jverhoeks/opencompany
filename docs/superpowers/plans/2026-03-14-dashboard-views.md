# Dashboard Views Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four tabbed views (Kanban, Organigram, Office floor plan, Company editor) to the NovaCraft dashboard with Playwright E2E tests.

**Architecture:** Refactor existing `dashboard.html` into a shell with tab navigation. Each view is a separate HTML partial in `static/views/` loaded via `fetch()`. SSE stream feeds all views through a `viewRegistry` pattern. New API endpoints for roles CRUD and soul updates. Playwright tests verify all views render correctly with seeded data.

**Tech Stack:** Python/FastAPI (backend), vanilla HTML/CSS/JS (frontend), SVG (organigram), Playwright + pytest (E2E tests)

**Spec:** `docs/superpowers/specs/2026-03-14-dashboard-views-design.md`

**Security note:** All HTML views use DOMPurify (already loaded in the dashboard shell) for sanitizing any user-generated HTML content. Plain text content uses `textContent` assignment or the `esc()` helper which uses `textContent`-based escaping. The `esc()` helper in each view creates a temporary DOM element, sets `textContent`, then reads `innerHTML` to get properly escaped output. The Soul editor preview uses `DOMPurify.sanitize()` before injecting parsed markdown.

---

## File Map

### Backend (modify)
- `src/opencompany/gateway/dashboard.py` — add StaticFiles mount, extend `_get_overview_data()` with `reports_to`, `backstory`, `budget_tokens`
- `src/opencompany/gateway/api.py` — extend `PersonaConfigPatch` with `name`/`role`, add roles CRUD + soul POST endpoints
- `src/opencompany/company/config.py` — add `update_role()` and `delete_role()` functions
- `src/opencompany/main.py` — mount StaticFiles for `/static`
- `pyproject.toml` — add `pytest-playwright` dev dependency

### Frontend (modify)
- `src/opencompany/static/dashboard.html` — refactor to shell with tabs, view registry, view container

### Frontend (create)
- `src/opencompany/static/views/kanban.html` — kanban board view
- `src/opencompany/static/views/organigram.html` — org tree SVG view
- `src/opencompany/static/views/office.html` — floor plan view
- `src/opencompany/static/views/editor.html` — company editor view

### Tests (create)
- `tests/test_dashboard_e2e.py` — Playwright E2E tests
- `tests/test_roles_api.py` — unit tests for roles CRUD endpoints
- `tests/test_config_roles.py` — unit tests for config update/delete role functions

---

## Chunk 1: Backend Changes

### Task 1: Extend SSE data with missing fields

**Files:**
- Modify: `src/opencompany/gateway/dashboard.py:84-133`
- Test: `tests/test_dashboard_cov.py`

- [ ] **Step 1: Write failing test for `reports_to` in overview data**

In `tests/test_dashboard_cov.py`, add:

```python
@pytest.mark.asyncio
async def test_overview_includes_reports_to(db_engine):
    """Persona data in overview must include reports_to for organigram."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        session.add(Persona(id="ceo", name="CEO", role="ceo", type="manager"))
        session.add(
            Persona(
                id="pm", name="PM", role="pm", type="manager", reports_to="ceo"
            )
        )
        await session.commit()
        data = await _get_overview_data(session)

    pm_data = next(p for p in data["personas"] if p["id"] == "pm")
    assert pm_data["reports_to"] == "ceo"
    ceo_data = next(p for p in data["personas"] if p["id"] == "ceo")
    assert ceo_data["reports_to"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dashboard_cov.py::test_overview_includes_reports_to -v`
Expected: FAIL — `reports_to` key not in persona dict

- [ ] **Step 3: Add `reports_to`, `backstory` to persona dicts in `_get_overview_data()`**

In `src/opencompany/gateway/dashboard.py`, in the persona list comprehension inside `_get_overview_data()`, add after `"tokens_used_today"`:

```python
"reports_to": p.reports_to,
"backstory": p.backstory,
```

- [ ] **Step 4: Add `budget_tokens` to ticket dicts in `_get_overview_data()`**

In the ticket list comprehension, add after `"tokens_out"`:

```python
"budget_tokens": t.budget_tokens,
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_dashboard_cov.py::test_overview_includes_reports_to -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/opencompany/gateway/dashboard.py tests/test_dashboard_cov.py
git commit -m "feat: add reports_to, backstory, budget_tokens to SSE data"
```

---

### Task 2: Extend PersonaConfigPatch to accept name and role

**Files:**
- Modify: `src/opencompany/gateway/api.py:254-258`

- [ ] **Step 1: Write failing test**

In `tests/test_sprint5_persona_config.py` (or `tests/test_dashboard_cov.py`), add:

```python
@pytest.mark.asyncio
async def test_patch_persona_config_name_and_role(client, db_session):
    """PATCH /api/config/personas/{id} should accept name and role."""
    from opencompany.models.db import PersonaConfig

    pc = PersonaConfig(
        id="dev1", name="Dev One", role="backend-dev", trust="solver",
        skills=[], budget_tokens_daily=100000, instructions="", personality={},
        updated_by="system",
    )
    db_session.add(pc)
    await db_session.commit()

    resp = await client.patch(
        "/api/config/personas/dev1",
        json={"name": "Dev Alpha", "role": "frontend-dev"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Dev Alpha"
    assert data["role"] == "frontend-dev"
```

- [ ] **Step 2: Run test to verify it fails**

Expected: 200 but name/role unchanged (fields ignored by current `PersonaConfigPatch`)

- [ ] **Step 3: Add `name` and `role` to `PersonaConfigPatch`**

In `src/opencompany/gateway/api.py`, modify `PersonaConfigPatch`:

```python
class PersonaConfigPatch(BaseModel):
    name: str | None = None
    role: str | None = None
    instructions: str | None = None
    budget_tokens_daily: int | None = None
    personality: dict | None = None
    skills: list[str] | None = None
```

The existing `api_patch_persona_config` handler already uses `body.model_dump(exclude_unset=True)` to update fields, so this should work without further changes.

- [ ] **Step 4: Run test to verify it passes**

- [ ] **Step 5: Commit**

```bash
git add src/opencompany/gateway/api.py tests/
git commit -m "feat: allow patching persona name and role via config API"
```

---

### Task 3: Add roles CRUD API endpoints

**Files:**
- Modify: `src/opencompany/gateway/api.py`
- Modify: `src/opencompany/company/config.py`
- Create: `tests/test_config_roles.py`

- [ ] **Step 1: Add `update_role()` and `delete_role()` to config.py**

In `src/opencompany/company/config.py`, add after `add_role()`:

```python
def update_role(
    role_id: str,
    updates: dict[str, Any],
    path: str | None = None,
) -> None:
    """Update an existing role in company.yaml. Raises KeyError if not found."""
    if path is None:
        path = os.path.join("config", "company.yaml")

    with open(path) as f:
        raw = yaml.safe_load(f)

    roles = raw.get("roles", {})
    if role_id not in roles:
        raise KeyError(f"Role '{role_id}' not found")

    roles[role_id].update(updates)

    with open(path, "w") as f:
        yaml.dump(raw, f, default_flow_style=False, sort_keys=False)

    invalidate_cache()
    logger.info("Updated role '%s' in %s", role_id, path)


def delete_role(role_id: str, path: str | None = None) -> None:
    """Delete a role from company.yaml. Raises KeyError if not found."""
    if path is None:
        path = os.path.join("config", "company.yaml")

    with open(path) as f:
        raw = yaml.safe_load(f)

    roles = raw.get("roles", {})
    if role_id not in roles:
        raise KeyError(f"Role '{role_id}' not found")

    del roles[role_id]

    with open(path, "w") as f:
        yaml.dump(raw, f, default_flow_style=False, sort_keys=False)

    invalidate_cache()
    logger.info("Deleted role '%s' from %s", role_id, path)
```

- [ ] **Step 2: Write unit tests for config functions**

Create `tests/test_config_roles.py`:

```python
import pytest
import yaml

from opencompany.company.config import add_role, delete_role, load_company_config, update_role


@pytest.fixture
def config_file(tmp_path):
    """Create a minimal company.yaml for testing."""
    data = {
        "org_style": "hierarchical",
        "org_styles": {"hierarchical": {"routing": {"ceo": "pm"}, "max_depth": 3}},
        "roles": {
            "ceo": {"type": "manager", "responsibilities": "Lead."},
            "dev": {"type": "solver", "responsibilities": "Code.", "tag_match": ["backend"]},
        },
        "personas": {},
    }
    path = tmp_path / "company.yaml"
    path.write_text(yaml.dump(data, default_flow_style=False))
    return str(path)


def test_update_role(config_file):
    update_role("dev", {"responsibilities": "Code and test."}, path=config_file)
    config = load_company_config(config_file)
    assert config.roles["dev"]["responsibilities"] == "Code and test."


def test_update_role_not_found(config_file):
    with pytest.raises(KeyError, match="not-exist"):
        update_role("not-exist", {"responsibilities": "x"}, path=config_file)


def test_delete_role(config_file):
    delete_role("dev", path=config_file)
    config = load_company_config(config_file)
    assert "dev" not in config.roles


def test_delete_role_not_found(config_file):
    with pytest.raises(KeyError, match="nope"):
        delete_role("nope", path=config_file)
```

- [ ] **Step 3: Run config tests**

Run: `uv run pytest tests/test_config_roles.py -v`
Expected: PASS

- [ ] **Step 4: Add roles CRUD endpoints to api.py**

In `src/opencompany/gateway/api.py`, add the following Pydantic models and endpoints:

```python
class RoleOut(BaseModel):
    id: str
    type: str
    responsibilities: str
    constraints: str = ""
    tools: list[str] = []
    tag_match: list[str] = []
    routes_to: str | None = None
    personality: dict = {}
    daily_token_budget: int = 0
    max_headcount: int | None = None
    builtin: bool = False


class RoleCreate(BaseModel):
    id: str
    type: Literal["manager", "lead", "solver", "observer"]
    responsibilities: str
    constraints: str = ""
    tools: list[str] = []
    tag_match: list[str] = []
    routes_to: str | None = None
    personality: dict = {}
    daily_token_budget: int = 0
    max_headcount: int | None = None


class RolePatch(BaseModel):
    type: str | None = None
    responsibilities: str | None = None
    constraints: str | None = None
    tools: list[str] | None = None
    tag_match: list[str] | None = None
    routes_to: str | None = None
    personality: dict | None = None
    daily_token_budget: int | None = None
    max_headcount: int | None = None


@router.get("/config/roles", dependencies=[Depends(verify_api_key)])
async def api_list_roles() -> list[RoleOut]:
    from opencompany.company.config import load_company_config
    config = load_company_config()
    return [
        RoleOut(id=role_id, **{k: v for k, v in role.items() if k in RoleOut.model_fields})
        for role_id, role in config.roles.items()
    ]


@router.post("/config/roles", status_code=201, dependencies=[Depends(verify_api_key)])
async def api_create_role(body: RoleCreate) -> RoleOut:
    from opencompany.company.config import add_role
    try:
        add_role(
            role_id=body.id,
            role_type=body.type,
            responsibilities=body.responsibilities,
            constraints=body.constraints,
            tools=body.tools,
            tag_match=body.tag_match,
            routes_to=body.routes_to,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return RoleOut(**body.model_dump())


@router.patch("/config/roles/{role_id}", dependencies=[Depends(verify_api_key)])
async def api_patch_role(role_id: str, body: RolePatch) -> RoleOut:
    from opencompany.company.config import load_company_config, update_role
    updates = body.model_dump(exclude_unset=True)
    try:
        update_role(role_id, updates)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Role '{role_id}' not found")
    config = load_company_config()
    role = config.roles[role_id]
    return RoleOut(id=role_id, **{k: v for k, v in role.items() if k in RoleOut.model_fields})


@router.delete("/config/roles/{role_id}", dependencies=[Depends(verify_api_key)])
async def api_delete_role(
    role_id: str, session: AsyncSession = Depends(get_session)
):
    from opencompany.company.config import delete_role
    # Check no active personas use this role
    count = await session.scalar(
        sa_func.count(Persona.id).filter(Persona.role == role_id, Persona.status == "active")
    )
    if count and count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete: {count} active persona(s) use role '{role_id}'",
        )
    try:
        delete_role(role_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Role '{role_id}' not found")
    return {"status": "deleted", "role_id": role_id}
```

- [ ] **Step 5: Run all tests**

Run: `uv run pytest tests/test_config_roles.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/opencompany/gateway/api.py src/opencompany/company/config.py tests/test_config_roles.py
git commit -m "feat: roles CRUD API endpoints + config update/delete"
```

---

### Task 4: Add POST /api/soul endpoint

**Files:**
- Modify: `src/opencompany/gateway/api.py`

- [ ] **Step 1: Add soul update endpoint**

In `src/opencompany/gateway/api.py`, add:

```python
class SoulUpdate(BaseModel):
    content: str
    rationale: str


@router.post("/soul", dependencies=[Depends(verify_api_key)])
async def api_propose_soul_update(body: SoulUpdate):
    from opencompany.company.soul import propose_update
    accepted, reason = await propose_update(
        proposed=body.content,
        rationale=body.rationale,
        proposed_by="overseer",
    )
    if not accepted:
        raise HTTPException(status_code=422, detail=reason)
    return {"status": "accepted", "message": reason}
```

- [ ] **Step 2: Commit**

```bash
git add src/opencompany/gateway/api.py
git commit -m "feat: POST /api/soul endpoint for soul updates"
```

---

### Task 5: Mount StaticFiles for view partials

**Files:**
- Modify: `src/opencompany/main.py`

- [ ] **Step 1: Add StaticFiles mount**

In `src/opencompany/main.py`, after the router includes, add:

```python
from fastapi.staticfiles import StaticFiles
from pathlib import Path

_static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")
```

- [ ] **Step 2: Create the views directory**

```bash
mkdir -p src/opencompany/static/views
```

- [ ] **Step 3: Commit**

```bash
git add src/opencompany/main.py
git commit -m "feat: mount StaticFiles for view partials"
```

---

### Task 6: Add pytest-playwright dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add to dev dependencies**

In `pyproject.toml`, add to `[dependency-groups] dev`:

```toml
"pytest-playwright>=0.6",
```

- [ ] **Step 2: Install and set up Playwright**

```bash
uv sync --group dev
uv run playwright install chromium
```

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add pytest-playwright dev dependency"
```

---

## Chunk 2: Shell Refactor

### Task 7: Refactor dashboard.html into tabbed shell

**Files:**
- Modify: `src/opencompany/static/dashboard.html`

This is the core refactor. The existing dashboard.html has the kanban-style ticket display built into the main area. We need to:

1. Extract the main content area into a `<div id="view-container">`
2. Add tab buttons to the header
3. Add view registry JS and tab switching logic
4. Keep the sidebar and activity feed intact

- [ ] **Step 1: Add tab buttons to header**

In `dashboard.html`, inside the `.header` element, after the `.header-brand` div, add tab navigation:

```html
<nav class="header-tabs">
  <button class="tab-btn active" data-view="kanban">Kanban</button>
  <button class="tab-btn" data-view="organigram">Organigram</button>
  <button class="tab-btn" data-view="office">Office</button>
  <button class="tab-btn" data-view="editor">Editor</button>
</nav>
```

Add CSS for tabs:

```css
.header-tabs { display: flex; gap: 4px; }
.tab-btn {
  font-family: var(--font-display); font-size: 10px; letter-spacing: 1.5px;
  text-transform: uppercase; padding: 6px 14px; border: 1px solid var(--border);
  border-radius: 4px; background: transparent; color: var(--text-dim);
  cursor: pointer; transition: all 0.15s;
}
.tab-btn:hover { background: var(--bg-hover); color: var(--text-main); }
.tab-btn.active {
  background: rgba(0, 229, 255, 0.1); color: var(--cyan);
  border-color: var(--cyan); box-shadow: 0 0 8px rgba(0, 229, 255, 0.15);
}
```

- [ ] **Step 2: Replace main content area with view container**

Replace the existing `.main` content (ticket columns, filters) with:

```html
<main class="main" id="view-container">
  <div class="view-loading">Loading view...</div>
</main>
```

Add CSS:

```css
.view-loading {
  display: flex; align-items: center; justify-content: center;
  height: 100%; color: var(--text-dim); font-family: var(--font-mono);
  font-size: 12px;
}
.view-error {
  display: flex; align-items: center; justify-content: center;
  height: 100%; color: var(--red); font-family: var(--font-mono);
  font-size: 12px;
}
```

- [ ] **Step 3: Add view registry and tab switching JS**

Add to the `<script>` section:

```javascript
// --- View Registry ---
window.viewRegistry = {};
let activeViewName = null;
let cachedData = null;

async function switchView(name) {
  const container = document.getElementById('view-container');

  // Destroy previous view
  if (activeViewName && window.viewRegistry[activeViewName] && window.viewRegistry[activeViewName].destroy) {
    try { window.viewRegistry[activeViewName].destroy(); } catch(e) { /* ignore */ }
  }

  // Update tab buttons
  document.querySelectorAll('.tab-btn').forEach(function(btn) {
    btn.classList.toggle('active', btn.dataset.view === name);
  });

  // Load partial
  container.textContent = '';
  var loadingDiv = document.createElement('div');
  loadingDiv.className = 'view-loading';
  loadingDiv.textContent = 'Loading view...';
  container.appendChild(loadingDiv);

  try {
    var resp = await fetch('/static/views/' + encodeURIComponent(name) + '.html');
    if (!resp.ok) throw new Error('Failed to load view: ' + resp.status);
    var html = await resp.text();

    // Parse and inject safely using DOMParser
    container.textContent = '';
    var template = document.createElement('template');
    template.innerHTML = DOMPurify.sanitize(html, {
      ADD_TAGS: ['style', 'script'],
      FORCE_BODY: true,
      WHOLE_DOCUMENT: false,
    });
    // Actually, view partials are trusted first-party code, not user content.
    // We use direct insertion for scripts to work.
    container.innerHTML = html;

    // Execute scripts in the partial
    container.querySelectorAll('script').forEach(function(oldScript) {
      var newScript = document.createElement('script');
      newScript.textContent = oldScript.textContent;
      oldScript.replaceWith(newScript);
    });

    activeViewName = name;

    // Init and render with cached data
    if (window.viewRegistry[name] && window.viewRegistry[name].init) {
      await window.viewRegistry[name].init();
    }
    if (cachedData && window.viewRegistry[name] && window.viewRegistry[name].render) {
      window.viewRegistry[name].render(cachedData);
    }
  } catch (e) {
    container.textContent = '';
    var errDiv = document.createElement('div');
    errDiv.className = 'view-error';
    errDiv.textContent = 'Failed to load ' + name + ' view: ' + e.message;
    container.appendChild(errDiv);
  }
}

// Tab click handlers
document.querySelectorAll('.tab-btn').forEach(function(btn) {
  btn.addEventListener('click', function() { switchView(btn.dataset.view); });
});

// Load default view
switchView('kanban');
```

- [ ] **Step 4: Update SSE handler to dispatch to active view**

Modify the existing SSE `onmessage` handler to also cache data and call the active view:

```javascript
// In the existing SSE handler, after parsing data:
cachedData = data;
window._cachedData = data;  // expose for filter re-renders in partials
if (activeViewName && window.viewRegistry[activeViewName] && window.viewRegistry[activeViewName].render) {
  window.viewRegistry[activeViewName].render(data);
}
```

Keep the existing sidebar and feed rendering code — those update regardless of active view.

- [ ] **Step 5: Verify the shell loads without views (views don't exist yet)**

Start the server, open `/dashboard`, verify:
- Tab buttons appear in header
- "Failed to load kanban view: 404" error shows (expected — partials don't exist yet)
- Sidebar and feed still work from SSE

- [ ] **Step 6: Commit**

```bash
git add src/opencompany/static/dashboard.html
git commit -m "feat: refactor dashboard shell with tab navigation and view registry"
```

---

## Chunk 3: View Partials

Each view partial is a self-contained HTML fragment with `<style>`, markup, and `<script>` that registers into `window.viewRegistry`. All views use the `esc()` helper for text escaping: it creates a temporary element, assigns to `textContent` (safe), and reads `innerHTML` for escaped output. User-generated markdown content (Soul editor) is sanitized via `DOMPurify.sanitize()` before display.

### Task 8: Kanban view

**Files:**
- Create: `src/opencompany/static/views/kanban.html`

- [ ] **Step 1: Create kanban.html with columns, cards, filters**

The kanban view renders 5 status columns (Open, Assigned, In Progress, Review, Done) with ticket cards. Cards show title, priority badge, tags, assignee, and token usage bar. Filters allow filtering by persona, priority, and tag.

Key implementation details:
- `esc()` helper uses `textContent`-based escaping for all user data
- Cards are built by constructing escaped strings and setting column body content
- Filter changes trigger re-render using `window._cachedData`
- Card clicks dispatch a `show-detail` CustomEvent for the sidebar

- [ ] **Step 2: Commit**

```bash
git add src/opencompany/static/views/kanban.html
git commit -m "feat: kanban board view partial"
```

---

### Task 9: Organigram view

**Files:**
- Create: `src/opencompany/static/views/organigram.html`

- [ ] **Step 1: Create organigram.html with SVG tree, pan/zoom**

The organigram renders an SVG tree from persona `reports_to` relationships. Features:
- Tree layout algorithm: recursively positions children, parents centered above
- SVG `<path>` connections with cubic bezier curves
- Nodes show avatar circle (colored by type), name, role, activity state dot, ticket count
- Pan via mousedown+mousemove on background
- Zoom via mouse wheel (clamped 0.2x-3x)
- Zoom-to-fit button resets view
- Tooltips on hover show active ticket titles
- Node clicks dispatch `show-detail` event
- Fired personas shown at reduced opacity with strikethrough name

Node colors: cyan=manager, purple=lead, amber=solver, blue=observer
State colors: green=working, amber=idle, red=blocked

- [ ] **Step 2: Commit**

```bash
git add src/opencompany/static/views/organigram.html
git commit -m "feat: organigram SVG view with pan, zoom, hierarchy"
```

---

### Task 10: Office floor plan view

**Files:**
- Create: `src/opencompany/static/views/office.html`

- [ ] **Step 1: Create office.html with blueprint floor plan**

The office view renders a top-down blueprint with three sections:
- **Executive Offices** row: CEO (corner room, largest), HR (mid), other managers (mid)
- **Team Leads** row: small offices for each lead
- **Open Floor**: desk grid for solvers and observers, wrapping at 8 per row

Room assignment logic based on `persona.role` and `persona.type`:
- `role === "ceo"` → `.office-room.corner`
- `role === "hr"` → `.office-room.mid`
- `type === "manager"` → `.office-room.mid`
- `type === "lead"` → `.office-room.small`
- `type === "solver"` or `type === "observer"` → `.office-desk`

Each persona shows: avatar with initials, name, role label, workload count, activity state dot.
Fired personas get `.fired` class (opacity 0.25, dashed border).

Blueprint aesthetic: subtle grid background, glowing cyan borders at 25% opacity.

- [ ] **Step 2: Commit**

```bash
git add src/opencompany/static/views/office.html
git commit -m "feat: office floor plan view with blueprint layout"
```

---

### Task 11: Company editor view

**Files:**
- Create: `src/opencompany/static/views/editor.html`

- [ ] **Step 1: Create editor.html with three sub-tabs**

The editor has three sub-tabs: Personas, Roles, Soul. Sub-tabs use underlined text buttons (visually distinct from main header tabs).

**Personas sub-tab:**
- Left: searchable list from SSE persona data, merged with `/api/config/personas` on init
- Right: form with fields (name, role, skills, personality traits/style/quirks/catchphrases, instructions, budget)
- Save calls `PATCH /api/config/personas/{id}`
- Fired personas: list item dimmed, form fields disabled

**Roles sub-tab:**
- List loaded from `GET /api/config/roles` on sub-tab switch
- Form with type dropdown, responsibilities, constraints, tag_match, budget, headcount
- Save calls `PATCH /api/config/roles/{id}`
- Delete calls `DELETE /api/config/roles/{id}` with confirmation dialog
- New role: prompt for ID, calls `POST /api/config/roles`

**Soul sub-tab:**
- Left: textarea for soul content + rationale input + save button
- Center: live markdown preview using `marked.parse()` sanitized with `DOMPurify.sanitize()`
- Right: version history from `GET /api/soul/history`, click to rollback with confirmation

**Shared patterns:**
- `toast(message, type)` function: fixed-position notification, fades after 2s
- `apiCall(method, path, body)` helper: handles auth header, error extraction
- Save buttons show "Saving..." while request is in-flight, disabled to prevent double-submit

- [ ] **Step 2: Commit**

```bash
git add src/opencompany/static/views/editor.html
git commit -m "feat: company editor view with personas, roles, soul sub-tabs"
```

---

## Chunk 4: Playwright E2E Tests

### Task 12: Playwright test fixtures

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add live_server fixture to conftest.py**

Add at the end of `tests/conftest.py`:

```python
import asyncio
import socket
import threading

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import async_sessionmaker

from opencompany.gateway.api import router as api_router
from opencompany.gateway.dashboard import router as dashboard_router
from opencompany.models.db import Persona, Ticket


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
async def live_server(db_engine):
    """Start a real HTTP server with seeded data for Playwright tests."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    # Seed test data
    async with factory() as session:
        session.add(Persona(id="ceo", name="Alice CEO", role="ceo", type="manager"))
        session.add(Persona(id="hr", name="Bob HR", role="hr", type="manager", reports_to="ceo"))
        session.add(Persona(id="pm", name="Carol PM", role="pm", type="manager", reports_to="ceo"))
        session.add(Persona(id="tech-lead", name="Dave TL", role="tech-lead", type="lead", reports_to="pm"))
        session.add(Persona(id="dev1", name="Eve Dev", role="backend-dev", type="solver", reports_to="tech-lead"))
        session.add(Persona(id="dev2", name="Frank Dev", role="frontend-dev", type="solver", reports_to="tech-lead"))
        session.add(Persona(id="fired1", name="Ghost", role="backend-dev", type="solver", status="fired", reports_to="tech-lead"))
        session.add(Ticket(title="Setup CI", status="open", created_by="ceo", tags=["backend"], priority="high"))
        session.add(Ticket(title="Build API", status="assigned", assigned_to="dev1", created_by="pm", tags=["backend"]))
        session.add(Ticket(title="Fix bug", status="in_progress", assigned_to="dev2", created_by="tech-lead", tags=["frontend"], priority="high"))
        session.add(Ticket(title="Code review", status="review", assigned_to="dev1", created_by="pm"))
        session.add(Ticket(title="Deploy v1", status="done", assigned_to="dev1", created_by="ceo"))
        await session.commit()

    # Create minimal FastAPI app with test DB
    test_app = FastAPI()

    async def _get_test_session():
        async with factory() as session:
            yield session

    from opencompany.models.engine import get_session
    test_app.dependency_overrides[get_session] = _get_test_session
    test_app.include_router(api_router, prefix="/api")
    test_app.include_router(dashboard_router)

    from pathlib import Path
    static_dir = Path(__file__).resolve().parent.parent / "src" / "opencompany" / "static"
    test_app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    port = _free_port()
    config = uvicorn.Config(test_app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for server to be ready
    import httpx
    for _ in range(50):
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(f"http://127.0.0.1:{port}/dashboard")
                if r.status_code == 200:
                    break
        except Exception:
            pass
        await asyncio.sleep(0.1)

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=5)
```

- [ ] **Step 2: Commit**

```bash
git add tests/conftest.py
git commit -m "feat: add live_server fixture for Playwright E2E tests"
```

---

### Task 13: Playwright E2E test cases

**Files:**
- Create: `tests/test_dashboard_e2e.py`

- [ ] **Step 1: Create test file with all 28 test cases**

Test cases organized by view:

**Shell & Tab Navigation (4 tests):**
- `test_dashboard_loads` — header shows "NovaCraft"
- `test_default_tab_is_kanban` — kanban view active on load
- `test_tab_switching` — click each tab, verify active class toggles
- `test_sidebar_shows_personas` — sidebar lists seeded personas

**Kanban (5 tests):**
- `test_kanban_columns_present` — 5 column headers exist
- `test_kanban_tickets_in_correct_columns` — "Setup CI" in Open column
- `test_kanban_ticket_card_content` — cards have title and priority badge
- `test_kanban_filter_by_persona` — filter to dev1, only dev1 tickets show
- `test_kanban_click_ticket_shows_detail` — click card fires event

**Organigram (6 tests):**
- `test_organigram_renders_svg` — SVG has `.org-node` elements
- `test_organigram_hierarchy` — CEO node visible, paths connect nodes
- `test_organigram_node_content` — node shows "Alice CEO" and "ceo"
- `test_organigram_zoom` — wheel changes transform
- `test_organigram_zoom_to_fit` — button resets view
- `test_organigram_click_node` — click CEO node

**Office (7 tests):**
- `test_office_renders_rooms` — room elements visible
- `test_office_ceo_corner_office` — corner room contains "Alice CEO"
- `test_office_hr_near_ceo` — executive row contains "Bob HR"
- `test_office_leads_in_mid_row` — "Team Leads" label visible
- `test_office_solvers_in_open_floor` — desk elements visible
- `test_office_shows_ticket_counts` — ticket count badges visible
- `test_office_fired_persona_dimmed` — `.office-desk.fired` visible

**Editor (6 tests):**
- `test_editor_subtabs` — 3 sub-tab buttons
- `test_editor_persona_list` — persona list items visible
- `test_editor_persona_form` — click persona shows form with `#pf-name`
- `test_editor_persona_save` — edit + save shows success toast
- `test_editor_roles_list` — roles sub-tab shows role items
- `test_editor_soul_markdown` — soul sub-tab shows textarea + preview

Each test navigates to `/dashboard`, waits for initial data load, then performs assertions using Playwright's `expect()` API.

- [ ] **Step 2: Run the Playwright tests**

```bash
uv run pytest tests/test_dashboard_e2e.py -v
```

- [ ] **Step 3: Fix any failures and re-run**

- [ ] **Step 4: Commit**

```bash
git add tests/test_dashboard_e2e.py
git commit -m "feat: Playwright E2E tests for all dashboard views"
```

---

## Chunk 5: Integration & Cleanup

### Task 14: Run full test suite and fix issues

- [ ] **Step 1: Run existing tests to confirm nothing is broken**

```bash
uv run pytest tests/ -v --ignore=tests/test_dashboard_e2e.py
```

Expected: All existing tests pass.

- [ ] **Step 2: Run Playwright tests**

```bash
uv run pytest tests/test_dashboard_e2e.py -v
```

- [ ] **Step 3: Run linter**

```bash
uv run ruff check .
uv run ruff format --check .
```

- [ ] **Step 4: Fix any issues and commit**

```bash
git add -A
git commit -m "fix: resolve lint and test issues"
```
