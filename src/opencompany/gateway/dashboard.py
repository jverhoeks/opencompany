"""Dashboard API: aggregated overview + SSE stream + control tower UI."""

import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from opencompany.gateway.api import verify_api_key
from opencompany.models.db import Persona, Ticket, WorkLog
from opencompany.models.engine import get_session

logger = logging.getLogger(__name__)

router = APIRouter()

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


async def _get_overview_data(session: AsyncSession) -> dict:
    """Fetch aggregated dashboard data (shared by REST and SSE endpoints)."""
    persona_result = await session.execute(select(Persona).where(Persona.status == "active"))
    personas = persona_result.scalars().all()

    # SQL-level status counts instead of Python-side loop
    count_result = await session.execute(
        select(Ticket.status, func.count(Ticket.id)).group_by(Ticket.status)
    )
    counts: dict[str, int] = dict(count_result.all())

    # SQL-level workload per persona instead of Python-side loop
    workload_result = await session.execute(
        select(Ticket.assigned_to, func.count(Ticket.id))
        .where(Ticket.assigned_to.isnot(None))
        .where(Ticket.status.in_(["assigned", "in_progress"]))
        .group_by(Ticket.assigned_to)
    )
    workloads: dict[str, int] = dict(workload_result.all())

    # Limit tickets to most recent 200
    ticket_result = await session.execute(
        select(Ticket).order_by(Ticket.created_at.desc()).limit(200)
    )
    tickets = ticket_result.scalars().all()

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
                "persona_id": entry.persona_id,
                "action": entry.action,
                "ticket_id": entry.ticket_id,
                "details": entry.details,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
            }
            for entry in logs
        ],
    }


@router.get("/dashboard")
async def serve_dashboard():
    return FileResponse(STATIC_DIR / "dashboard.html", media_type="text/html")


@router.get("/api/dashboard/overview", dependencies=[Depends(verify_api_key)])
async def dashboard_overview(session: AsyncSession = Depends(get_session)):
    return await _get_overview_data(session)


@router.get("/api/dashboard/stream")
async def dashboard_stream(session: AsyncSession = Depends(get_session)):
    async def event_generator():
        while True:
            data = await _get_overview_data(session)
            yield f"data: {json.dumps(data, default=str)}\n\n"
            await asyncio.sleep(3)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
