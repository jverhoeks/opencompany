from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opencompany.agents.runner import run_persona
from opencompany.events.bus import publish
from opencompany.models.db import Persona, Ticket
from opencompany.models.engine import get_session

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
async def api_list_personas(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Persona).where(Persona.status == "active"))
    return result.scalars().all()


@router.get("/personas/{persona_id}", response_model=PersonaOut)
async def api_get_persona(persona_id: str, session: AsyncSession = Depends(get_session)):
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
async def api_list_tickets(status: str = "open", session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Ticket).where(Ticket.status == status))
    return result.scalars().all()


@router.post("/tickets", response_model=TicketOut)
async def api_create_ticket(body: TicketCreate, session: AsyncSession = Depends(get_session)):
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
    await publish("ticket.created", {"ticket_id": ticket.id})
    return ticket


# --- Chat endpoint ---


class ChatRequest(BaseModel):
    persona_id: str
    message: str


class ChatResponse(BaseModel):
    response: str


@router.post("/chat", response_model=ChatResponse)
async def api_chat(body: ChatRequest, session: AsyncSession = Depends(get_session)):
    persona = await session.get(Persona, body.persona_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")

    result = await run_persona(persona, body.message)
    return ChatResponse(response=result)
