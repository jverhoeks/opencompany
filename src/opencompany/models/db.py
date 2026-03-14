from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from opencompany.models.base import Base


class Persona(Base):
    __tablename__ = "personas"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    role: Mapped[str]
    type: Mapped[str] = mapped_column(index=True)  # observer | solver | reviewer | manager
    reports_to: Mapped[str | None] = mapped_column(ForeignKey("personas.id"), default=None)
    skills: Mapped[list] = mapped_column(JSONB, default_factory=list)
    watches: Mapped[list] = mapped_column(JSONB, default_factory=list)
    picks_up: Mapped[list] = mapped_column(JSONB, default_factory=list)
    tools: Mapped[list] = mapped_column(JSONB, default_factory=list)
    model_id: Mapped[str | None] = mapped_column(default=None)
    daily_token_budget: Mapped[int] = mapped_column(default=0)
    tokens_used_today: Mapped[int] = mapped_column(default=0)
    budget_reset_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=None,
    )
    backstory: Mapped[str] = mapped_column(default="")
    status: Mapped[str] = mapped_column(default="active", index=True)  # active | fired
    activity_state: Mapped[str] = mapped_column(default="idle")  # idle | working | blocked
    created_by: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default_factory=lambda: datetime.now(UTC),
    )


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True, init=False, autoincrement=True)
    title: Mapped[str]
    description: Mapped[str] = mapped_column(default="")
    priority: Mapped[str] = mapped_column(default="medium")
    status: Mapped[str] = mapped_column(default="open", index=True)
    tags: Mapped[list] = mapped_column(JSONB, default_factory=list)
    created_by: Mapped[str] = mapped_column(default="")
    assigned_to: Mapped[str | None] = mapped_column(default=None, index=True)
    reviewed_by: Mapped[str | None] = mapped_column(default=None)
    context: Mapped[dict] = mapped_column(JSONB, default_factory=dict)
    result: Mapped[str | None] = mapped_column(default=None)
    tokens_in: Mapped[int] = mapped_column(default=0)
    tokens_out: Mapped[int] = mapped_column(default=0)
    budget_tokens: Mapped[int] = mapped_column(default=4000)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default_factory=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default_factory=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


# TODO: PersonaMemory is used by the agent memory subsystem but has no
# read/write paths wired up yet. Wire up or remove once agents land.
class PersonaMemory(Base):
    __tablename__ = "persona_memory"

    id: Mapped[int] = mapped_column(primary_key=True, init=False, autoincrement=True)
    persona_id: Mapped[str] = mapped_column(ForeignKey("personas.id"), index=True)
    type: Mapped[str]  # fact | decision | interaction | preference
    content: Mapped[str]
    related_to: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default_factory=lambda: datetime.now(UTC),
    )


class WorkLog(Base):
    __tablename__ = "work_log"

    id: Mapped[int] = mapped_column(primary_key=True, init=False, autoincrement=True)
    persona_id: Mapped[str] = mapped_column(ForeignKey("personas.id"))
    action: Mapped[str]  # created | picked_up | solved | reviewed | rejected
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"), default=None)
    details: Mapped[str] = mapped_column(default="")
    duration_sec: Mapped[int | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default_factory=lambda: datetime.now(UTC),
        index=True,
    )


class PolicyDocument(Base):
    __tablename__ = "policy_documents"

    id: Mapped[int] = mapped_column(primary_key=True, init=False, autoincrement=True)
    title: Mapped[str]
    content: Mapped[str]  # markdown body
    author_id: Mapped[str] = mapped_column(ForeignKey("personas.id"))
    status: Mapped[str] = mapped_column(default="draft", index=True)
    approved_by: Mapped[str | None] = mapped_column(default=None)
    tags: Mapped[list] = mapped_column(JSONB, default_factory=list)
    applies_to: Mapped[list] = mapped_column(JSONB, default_factory=list)
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default_factory=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default_factory=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class PersonaConfig(Base):
    """Live editable config for a persona. Loaded by prompts.py at each run."""

    __tablename__ = "persona_configs"

    id: Mapped[str] = mapped_column(primary_key=True)  # matches personas.id
    name: Mapped[str]
    role: Mapped[str]
    trust: Mapped[str] = mapped_column(default="solver")
    skills: Mapped[list] = mapped_column(JSONB, default_factory=list)
    budget_tokens_daily: Mapped[int] = mapped_column(default=0)
    instructions: Mapped[str] = mapped_column(default="")
    personality: Mapped[dict] = mapped_column(JSONB, default_factory=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default_factory=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    updated_by: Mapped[str] = mapped_column(default="system")


class CompanySnapshot(Base):
    """Append-only log of company state. Written on interval + task completion."""

    __tablename__ = "company_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, init=False, autoincrement=True)
    trigger: Mapped[str]  # interval | tasks_complete | manual
    snapshot: Mapped[dict] = mapped_column(JSONB, default_factory=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default_factory=lambda: datetime.now(UTC),
    )


class OverseerMessage(Base):
    __tablename__ = "overseer_messages"

    id: Mapped[int] = mapped_column(primary_key=True, init=False, autoincrement=True)
    persona_id: Mapped[str] = mapped_column(ForeignKey("personas.id"), index=True)
    message: Mapped[str]
    reply: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default_factory=lambda: datetime.now(UTC),
    )
    replied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=None,
    )
