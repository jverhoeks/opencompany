"""initial schema

Revision ID: 93e48caf61e5
Revises:
Create Date: 2026-02-17

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "93e48caf61e5"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "personas",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("reports_to", sa.String(), nullable=True),
        sa.Column("skills", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("watches", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("picks_up", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tools", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model_id", sa.String(), nullable=True),
        sa.Column("backstory", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["reports_to"], ["personas.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("priority", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("assigned_to", sa.String(), nullable=True),
        sa.Column("reviewed_by", sa.String(), nullable=True),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result", sa.String(), nullable=True),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["tickets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "persona_memory",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("persona_id", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("related_to", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["persona_id"], ["personas.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "work_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("persona_id", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=True),
        sa.Column("details", sa.String(), nullable=False),
        sa.Column("duration_sec", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["persona_id"], ["personas.id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("peer", sa.String(), nullable=False),
        sa.Column("persona_id", sa.String(), nullable=False),
        sa.Column("transcript_path", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["persona_id"], ["personas.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("sessions")
    op.drop_table("work_log")
    op.drop_table("persona_memory")
    op.drop_table("tickets")
    op.drop_table("personas")
