# Roles-as-Config Architecture

**Date:** 2026-02-18
**Status:** Approved

## Problem

Prompts, routing rules, and role definitions are hardcoded in Python (`prompts.py`, `engine.py`). This makes the system rigid — you can't change roles, add new ones, or switch organization styles without editing code.

## Design Decisions

1. **Roles are config templates, personas are instances.** `company.yaml` defines a role catalog with responsibilities, constraints, tools, and routing. Personas reference a role.
2. **Only CEO + HR are built-in.** Everything else is hired at runtime.
3. **CEO + HR can invent new roles.** A `create_role` tool lets them define entirely new roles that persist to YAML.
4. **Organization styles are routing presets with overrides.** `dictator` (flat), `hierarchical` (chain of command), `holacracy` (self-steering circles).
5. **Collaborative hiring.** CEO creates tickets with hints/tags. HR reads role catalog and hires the right people.
6. **Persistent personas.** Once hired, personas stay across sessions. CEO can fire/restructure.
7. **Hybrid config.** YAML has structured attributes (responsibilities, constraints, tools). Python assembles these into prompts at runtime.

## YAML Structure

```yaml
org_style: hierarchical

org_styles:
  dictator:
    description: "Flat structure. CEO directly assigns to workers."
    routing: { ceo: solver }
    max_depth: 1
  hierarchical:
    description: "Chain of command. CEO → PM → Leads → Workers."
    routing: { ceo: pm, pm: lead, lead: solver }
    max_depth: 3
  holacracy:
    description: "Self-steering circles. Tickets route to matching circle."
    routing: { default: circle }
    max_depth: 1

roles:
  <role-id>:
    builtin: true|false      # only CEO + HR are builtin
    type: manager|lead|solver
    responsibilities: "..."
    constraints: "..."
    tools: [tool1, tool2]
    tag_match: [tag1, tag2]  # tickets with these tags route here
    routes_to: <target-type> # where this role's created tickets go next

personas:
  <persona-id>:
    role: <role-id>
    name: "Human Name"
    backstory: "Background story."
```

## Python Changes

### `company/config.py` (new)
Load/cache/validate `company.yaml`. Functions: `load_company_config()`, `get_role()`, `get_org_routing()`.

### `agents/prompts.py` (rewrite)
Thin assembler. Reads role config, builds prompt from: persona identity + role responsibilities/constraints + universal rules. No hardcoded `_ROLE_INSTRUCTIONS`.

### `company/engine.py` (modify)
Config-driven routing. Reads `org_styles[active].routing` and `role.tag_match`. No hardcoded `_LEAD_ROUTING`.

### `company/personas.py` (modify)
`hire_persona` looks up role catalog for tools/type/tag_match. `create_role` writes new roles to YAML.

### `agents/tools/company.py` (modify)
Add `create_role` tool for CEO + HR.

## Routing Flow (hierarchical example)

1. User → CEO → creates ticket tagged `[product, backend]`
2. CEO → creates HR ticket: "need tech lead + devs"
3. HR hires tech-lead, backend-dev, frontend-dev from role catalog
4. Engine routes CEO ticket → PM (routing: `ceo: pm`)
5. PM breaks down → sub-tickets tagged `backend`, `frontend`
6. Engine routes → tech-lead (tag_match includes `backend`, `frontend`)
7. Tech-lead creates dev tickets → engine routes to solver (routing: `lead: solver`)
8. Solvers execute, produce code
