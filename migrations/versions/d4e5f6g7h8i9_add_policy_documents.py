"""add policy_documents table

Revision ID: d4e5f6g7h8i9
Revises: c3d4e5f6g7h8
Create Date: 2026-02-23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d4e5f6g7h8i9"
down_revision: str = "c3d4e5f6g7h8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "policy_documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("author_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("approved_by", sa.String(), nullable=True),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("applies_to", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["personas.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_policy_documents_status", "policy_documents", ["status"])


def downgrade() -> None:
    op.drop_index("ix_policy_documents_status", "policy_documents")
    op.drop_table("policy_documents")
