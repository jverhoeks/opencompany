"""add activity_state and overseer_messages

Revision ID: a1b2c3d4e5f6
Revises: 93e48caf61e5
Create Date: 2026-02-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "93e48caf61e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "personas",
        sa.Column("activity_state", sa.String(), nullable=False, server_default="idle"),
    )

    op.create_table(
        "overseer_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("persona_id", sa.String(), nullable=False),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("reply", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["persona_id"], ["personas.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_overseer_messages_persona_id", "overseer_messages", ["persona_id"])


def downgrade() -> None:
    op.drop_index("ix_overseer_messages_persona_id", "overseer_messages")
    op.drop_table("overseer_messages")
    op.drop_column("personas", "activity_state")
