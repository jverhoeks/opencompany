"""Dashboard API: aggregated overview + serve the control tower UI."""

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opencompany.models.db import Persona, Ticket, WorkLog
from opencompany.models.engine import get_session

router = APIRouter()

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@router.get("/dashboard")
async def serve_dashboard():
    return FileResponse(STATIC_DIR / "dashboard.html", media_type="text/html")


@router.get("/api/dashboard/overview")
async def dashboard_overview(session: AsyncSession = Depends(get_session)):
    persona_result = await session.execute(select(Persona).where(Persona.status == "active"))
    personas = persona_result.scalars().all()

    ticket_result = await session.execute(select(Ticket))
    tickets = ticket_result.scalars().all()

    # Workload: count of active tickets per persona
    workloads: dict[str, int] = {}
    for t in tickets:
        if t.assigned_to and t.status in ("assigned", "in_progress"):
            workloads[t.assigned_to] = workloads.get(t.assigned_to, 0) + 1

    counts: dict[str, int] = {}
    for t in tickets:
        counts[t.status] = counts.get(t.status, 0) + 1

    log_result = await session.execute(
        select(WorkLog).order_by(WorkLog.created_at.desc()).limit(50)
    )
    logs = log_result.scalars().all()

    return {
        "personas": [
            {
                "id": p.id,
                "name": p.name,
                "role": p.role,
                "type": p.type,
                "skills": p.skills,
                "workload": workloads.get(p.id, 0),
            }
            for p in personas
        ],
        "tickets": [
            {
                "id": t.id,
                "title": t.title,
                "description": t.description,
                "priority": t.priority,
                "status": t.status,
                "tags": t.tags,
                "assigned_to": t.assigned_to,
                "created_by": t.created_by,
                "result": t.result,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in tickets
        ],
        "status_counts": counts,
        "work_log": [
            {
                "persona_id": l.persona_id,
                "action": l.action,
                "ticket_id": l.ticket_id,
                "details": l.details,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ],
    }
