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
- Each partial registers itself via a global `window.viewRegistry[name] = { init(), render(data) }` pattern
- Tab switch: fetch partial HTML → inject into container → call `init()` → immediately `render()` with latest cached data

### Backend Changes

- Serve view partials via existing static file serving (add `views/` subdirectory to `STATIC_DIR`)
- New route or extend existing: `GET /static/views/{name}.html`

## View 1: Kanban Board

### Layout

Horizontal swim lane columns, left to right: **Open → Assigned → In Progress → Review → Done/Closed**

### Ticket Cards

Each card displays:
- Title (truncated to 2 lines)
- Priority badge (color-coded: amber=high, cyan=medium, dim=low)
- Tags as small pills
- Assigned persona avatar + name
- Created by (small text)
- Token usage indicator (thin bar showing tokens_in + tokens_out vs budget_tokens)

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

- CEO at top, lines flow down via `reports_to` relationships
- Each level spreads horizontally
- Simple layered layout calculated in JS (manager layer → lead layer → solver layer)
- Connections rendered as SVG `<path>` with subtle curves

### Nodes

Each node shows:
- Persona avatar circle (colored by type: cyan=manager, green=solver, amber=lead, purple=observer)
- Name + role title
- Activity state indicator dot (green=working, amber=idle, red=blocked)
- Active ticket count badge
- Hover: tooltip with current ticket titles

### Interactions

- Mouse wheel → zoom in/out
- Click + drag background → pan
- Click node → shows persona detail in right sidebar
- "Zoom to fit" button resets view

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

Based on persona type and role from SSE data:
- `type: manager` + `role: ceo` → corner office (largest room)
- `type: manager` + `role: hr` → adjacent to CEO
- `type: manager` (pm, others) → mid-size offices along top row
- `type: lead` → small offices in middle row
- `type: solver` → desks in open floor area, side by side

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
- Open floor wraps desks to new rows as needed
- No animations for now (future enhancement)

## View 4: Company Editor

### Sub-tabs

Three sub-tabs within the editor: **Personas** | **Roles** | **Soul**

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
- Save → `PATCH /api/config/personas/{id}`
- Fired personas shown dimmed, not editable

### Roles Tab

- List of roles from config
- Edit form per role:
  - Type (dropdown: manager/lead/solver/observer)
  - Responsibilities (textarea)
  - Constraints (textarea)
  - Tools (checkbox list from available tools)
  - Personality template (traits, style, quirks, catchphrases)
  - Daily token budget (number)
  - Max headcount (number)
  - Tag match (tag input)
- New role button
- Delete role (only if no active personas use it)

### Soul Tab

- Full-width markdown editor (textarea with live preview via marked.js)
- Version history list on the side (from SoulVersion table)
- Save → `POST /api/soul` (propose update)
- Rollback button per version → `POST /api/soul/rollback/{version}`

### New API Endpoints

Required for the Roles sub-tab:
- `GET /api/config/roles` — list all roles from config
- `POST /api/config/roles` — create new role
- `PATCH /api/config/roles/{role_id}` — edit role
- `DELETE /api/config/roles/{role_id}` — delete role

## Shared Conventions

- All views use existing CSS variables (--bg-deep, --bg-panel, --cyan, --green, etc.)
- All views use existing fonts (Orbitron, Outfit, JetBrains Mono)
- No external JS frameworks — vanilla JS only, consistent with existing dashboard
- marked.js + DOMPurify already loaded in shell for markdown rendering
- Responsive within the center panel area (not mobile-responsive, desktop dashboard)

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
  → API updates DB
  → next SSE tick reflects change
  → all views auto-update
```
