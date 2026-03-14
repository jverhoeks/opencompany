# Dashboard Views: Kanban, Organigram, Office Floor Plan, Company Editor

## Overview

Extend the existing NovaCraft Control Tower dashboard with four tabbed views in the center panel. The shell (header, sidebar, activity feed) remains; the center content swaps based on the active tab. Each view is a separate HTML partial loaded via `fetch()`.

## Architecture

### File Structure

```
src/opencompany/static/
  dashboard.html          # shell (header, sidebar, feed, tab logic, SSE)
  views/
    kanban.html           # kanban board (default view)
    organigram.html       # interactive org tree
    office.html           # top-down floor plan
    editor.html           # company editor (personas, roles, soul)
```

### Shell & Navigation

- Header bar gets tab buttons: **Kanban** (default) | **Organigram** | **Office** | **Editor**
- Styled as cyberpunk buttons with cyan accent on active tab
- Center panel becomes a `<div id="view-container">` that loads partials
- SSE stream (`/api/dashboard/stream`) feeds all views — shell receives data and calls active view's `render(data)` callback
- Each partial registers itself via a global `window.viewRegistry[name] = { init(), render(data), destroy() }` pattern
  - `init()` — may return a Promise for async setup (e.g. SVG canvas creation)
  - `render(data)` — update DOM from SSE data
  - `destroy()` — cleanup event listeners, SVG elements, timers when switching away
- Tab switch: call `destroy()` on previous view → fetch partial HTML → inject into container → call `init()` → immediately `render()` with latest cached data
- If a partial fails to load (404, network error), show an error message in the view container
- SSE reconnection: if the EventSource connection drops, auto-reconnect with exponential backoff (existing pattern in dashboard.html)

### Backend Changes

**Static file serving:** Add a `StaticFiles` mount for the `static/` directory (the current dashboard only has a single hardcoded `FileResponse`). This enables serving `views/*.html` without individual routes.

**SSE data additions** — add to `_get_overview_data()` persona objects:
- `reports_to` (string, nullable) — needed for organigram hierarchy
- `backstory` (string) — useful for persona detail view

**Ticket data additions** — add to `_get_overview_data()` ticket objects:
- `budget_tokens` (int) — needed for token usage bar on kanban cards

**New API endpoints:**

Roles CRUD (reads/writes `company.yaml` via existing `config.add_role()` pattern):
- `GET /api/config/roles` — list all roles from config
- `POST /api/config/roles` — create new role (writes to YAML)
- `PATCH /api/config/roles/{role_id}` — edit role (writes to YAML)
- `DELETE /api/config/roles/{role_id}` — delete role (only if no active personas use it)

Soul update:
- `POST /api/soul` — propose soul update (accepts `{content, rationale}`, calls `soul.propose_update()` internally)

**Persona config patch extension** — extend existing `PATCH /api/config/personas/{id}` to also accept `name` and `role` fields (currently only supports `instructions`, `budget_tokens_daily`, `personality`, `skills`).

## View 1: Kanban Board

### Layout

Horizontal swim lane columns, left to right: **Open → Assigned → In Progress → Review → Done/Closed**

This is a redesign from the existing 4-column layout. The Ticket model already supports all these statuses: `open, assigned, in_progress, review, done, rejected, closed`.

### Ticket Cards

Each card displays:
- Title (truncated to 2 lines)
- Priority badge (color-coded: amber=high, cyan=medium, dim=low)
- Tags as small pills
- Assigned persona avatar + name
- Created by (small text)
- Token usage indicator (thin bar showing `tokens_in + tokens_out` vs `budget_tokens`)

### Interactions

- Click card → expands detail in right sidebar (temporarily replaces activity feed)
- Column headers show ticket count
- No drag-and-drop (tickets are agent-assigned, not human-assigned)

### Filtering

Top bar with client-side filters:
- Assigned to (dropdown of personas)
- Tags (multi-select)
- Priority (high/medium/low)

### Rejected/Closed

Collapsed section at bottom, not a full column.

## View 2: Organigram

### Rendering

SVG canvas with pan and zoom. Top-down hierarchy tree.

### Tree Layout

- CEO at top, lines flow down via `reports_to` relationships (now included in SSE data)
- Each level spreads horizontally
- Simple layered layout calculated in JS (manager layer → lead layer → solver layer)
- Connections rendered as SVG `<path>` with subtle curves

### Nodes

Each node shows:
- Persona avatar circle (colored by type: cyan=manager, purple=lead, amber=solver, blue=observer — distinct from activity state colors to avoid confusion)
- Name + role title
- Activity state indicator dot (green=working, amber=idle, red=blocked) — small dot in corner, visually distinct from the avatar fill color
- Active ticket count badge
- Hover: tooltip with current ticket titles

### Interactions

- Mouse wheel → zoom in/out
- Click + drag background → pan
- Click node → shows persona detail in right sidebar
- "Zoom to fit" button — floating in top-right corner of the SVG canvas

### Fired Personas

Shown dimmed/ghosted with strikethrough name to preserve org history.

## View 3: Office Floor Plan

### Style

Top-down 2D blueprint. Dark background, thin glowing lines (cyan at 30% opacity) for walls. Fits the existing NovaCraft cyberpunk aesthetic.

### Room Layout

```
┌─────────────────────────────────────────────┐
│  ┌──────────┐ ┌────────┐  ┌────────┐       │
│  │ CEO      │ │ HR     │  │ PM     │       │
│  │ (corner) │ │        │  │        │       │
│  └──────────┘ └────────┘  └────────┘       │
│                                             │
│  ┌────────┐ ┌────────┐                     │
│  │Tech    │ │Mktg    │   (other leads)     │
│  │Lead    │ │Lead    │                     │
│  └────────┘ └────────┘                     │
│                                             │
│  ┌─────────────────────────────────────┐   │
│  │  Open floor — Developers / Solvers  │   │
│  │  ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐   │   │
│  │  │d │ │d │ │d │ │d │ │d │ │d │   │   │
│  │  └──┘ └──┘ └──┘ └──┘ └──┘ └──┘   │   │
│  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

### Room Assignment Logic (client-side)

Based on `persona.role` field from SSE data:
- `role === "ceo"` → corner office (largest room)
- `role === "hr"` → adjacent to CEO
- `type === "manager"` (other managers) → mid-size offices along top row
- `type === "lead"` → small offices in middle row
- `type === "solver"` → desks in open floor area, side by side

### Persona Display

- Small desk rectangle with avatar circle
- Name label below
- Active ticket count badge
- Activity state glow (green=working, amber=idle, red=blocked)

### Dynamic Behavior

- Floor plan re-renders from persona data each SSE tick
- When personas are hired, desks/offices appear
- Fired personas' desks show as empty/dimmed
- Lead row extends if more leads hired
- Open floor wraps desks to new rows (max 8 per row, then scrollable vertically within the open floor area)
- The entire floor plan fits within the view container; if it overflows, the container scrolls
- No animations for now (future enhancement)

## View 4: Company Editor

### Sub-tabs

Three sub-tabs within the editor: **Personas** | **Roles** | **Soul**

Sub-tabs are rendered as smaller, underlined text buttons below the main view area header — visually distinct from the main header tabs (which are full cyberpunk buttons).

### Editor Feedback

All editor forms share these patterns:
- **Save button** shows loading spinner during request
- **Success**: brief green "Saved" toast that fades after 2 seconds
- **Error**: red toast with error message from API response
- **Delete**: confirmation dialog ("Are you sure?") before destructive actions

### Personas Tab

- Left panel: searchable list of all personas (active + fired)
- Right panel: edit form for selected persona
- Editable fields:
  - Name (text)
  - Role (dropdown from roles catalog)
  - Skills (tag input)
  - Personality: traits (list), communication_style (text), quirks (list), catchphrases (list)
  - Instructions (textarea)
  - Daily token budget (number)
- Save → `PATCH /api/config/personas/{id}` (extended to accept name, role)
- Fired personas shown dimmed, not editable

### Roles Tab

- List of roles from config (loaded via `GET /api/config/roles`)
- Edit form per role:
  - Type (dropdown: manager/lead/solver/observer)
  - Responsibilities (textarea)
  - Constraints (textarea)
  - Tools (checkbox list from available tools)
  - Personality template (traits, style, quirks, catchphrases)
  - Daily token budget (number)
  - Max headcount (number)
  - Tag match (tag input)
- New role button → `POST /api/config/roles`
- Delete role → `DELETE /api/config/roles/{role_id}` (only if no active personas use it)

Roles are stored in `company.yaml` (not a DB table). The CRUD endpoints read/write YAML via the existing `config` module pattern.

### Soul Tab

- Full-width markdown editor (textarea with live preview via marked.js, sanitized with DOMPurify)
- Version history list on the side (from SoulVersion table via `GET /api/soul/history`)
- Save → `POST /api/soul` with `{content, rationale}` (new endpoint)
- Rollback button per version → `POST /api/soul/rollback/{version}`

## Shared Conventions

- All views use existing CSS variables (--bg-deep, --bg-panel, --cyan, --green, etc.)
- All views use existing fonts (Orbitron, Outfit, JetBrains Mono)
- No external JS frameworks — vanilla JS only, consistent with existing dashboard
- marked.js + DOMPurify already loaded in shell for markdown rendering
- Desktop-only (not mobile-responsive)

## Data Flow

```
SSE /api/dashboard/stream
  → shell receives JSON every 3s
  → shell caches latest data
  → shell calls activeView.render(data)
  → view updates its DOM from data
```

For editor mutations:
```
Editor form submit
  → fetch() POST/PATCH/DELETE to API
  → show loading spinner on save button
  → on success: green toast, next SSE tick reflects change
  → on error: red toast with error message
  → all views auto-update via SSE
```

## Testing: Playwright E2E

### Setup

Add `pytest-playwright` as a dev dependency. Tests live in `tests/test_dashboard_e2e.py`.

The test server uses the same in-memory SQLite + ASGI pattern as existing e2e tests (`test_e2e.py`), but served via `uvicorn` on a random port so Playwright can connect via a real browser.

**New dependency:** `pytest-playwright` (pulls in `playwright` automatically).

**Fixture: `live_server`** — starts the FastAPI app on `localhost:<random_port>` with seeded test data (CEO, HR, PM, tech-lead, 2 solvers, 5 tickets in various statuses), yields the base URL, shuts down after the test.

**Fixture: `seeded_data`** — inserts the test personas and tickets into the in-memory DB so all views have data to render.

### Test File Structure

```
tests/
  test_dashboard_e2e.py      # all Playwright tests
  conftest.py                # existing + new live_server fixture
```

### Test Cases

#### Shell & Tab Navigation
- `test_dashboard_loads` — navigate to `/dashboard`, verify header with "NovaCraft" title is visible
- `test_tab_switching` — click each tab (Kanban, Organigram, Office, Editor), verify view container content changes
- `test_default_tab_is_kanban` — on load, Kanban view is active
- `test_sidebar_shows_personas` — sidebar lists all seeded personas with names

#### Kanban View
- `test_kanban_columns_present` — verify 5 column headers (Open, Assigned, In Progress, Review, Done)
- `test_kanban_tickets_in_correct_columns` — seeded tickets appear in columns matching their status
- `test_kanban_ticket_card_content` — a ticket card shows title, priority badge, tags, assigned persona
- `test_kanban_filter_by_persona` — select a persona in the filter, verify only their tickets show
- `test_kanban_click_ticket_shows_detail` — click a ticket card, verify detail panel appears in sidebar

#### Organigram View
- `test_organigram_renders_svg` — switch to Organigram tab, verify SVG element exists with nodes
- `test_organigram_hierarchy` — CEO node at top, solvers at bottom, connected by paths
- `test_organigram_node_content` — nodes show persona name, role, activity state dot
- `test_organigram_zoom` — use mouse wheel to zoom, verify SVG transform changes
- `test_organigram_zoom_to_fit` — click zoom-to-fit button, verify view resets
- `test_organigram_click_node` — click a persona node, verify detail in sidebar

#### Office Floor Plan
- `test_office_renders_rooms` — switch to Office tab, verify room elements exist
- `test_office_ceo_corner_office` — CEO persona is in the largest room (corner office)
- `test_office_hr_near_ceo` — HR persona is in a room adjacent to CEO
- `test_office_leads_in_mid_row` — lead personas appear in the middle row offices
- `test_office_solvers_in_open_floor` — solver personas appear in the open floor area at desks
- `test_office_shows_ticket_counts` — each persona desk/room shows their active ticket count
- `test_office_fired_persona_dimmed` — a fired persona's desk appears dimmed

#### Company Editor
- `test_editor_subtabs` — switch to Editor tab, verify 3 sub-tabs (Personas, Roles, Soul)
- `test_editor_persona_list` — Personas sub-tab shows list of all personas
- `test_editor_persona_form` — click a persona, verify form populates with their data
- `test_editor_persona_save` — edit a persona field, click save, verify success toast, verify API was called
- `test_editor_roles_list` — Roles sub-tab shows list of roles from config
- `test_editor_role_form` — click a role, verify form with type, responsibilities, tools checkboxes
- `test_editor_soul_markdown` — Soul sub-tab shows textarea and preview panel
- `test_editor_soul_version_history` — version history list shows SoulVersion entries
- `test_editor_fired_persona_not_editable` — fired persona in list is dimmed, form fields disabled

### SSE Testing Strategy

Playwright tests do NOT rely on SSE streaming for initial data. Instead:
- The `live_server` fixture seeds data before the browser connects
- The dashboard's initial `fetch()` to `/api/dashboard/overview` provides first render
- For tests that verify live updates (optional, stretch goal), use `page.evaluate()` to trigger a mock SSE event

### Running

```bash
uv run playwright install chromium    # one-time browser install
uv run pytest tests/test_dashboard_e2e.py -v
```
