"""add budget columns to personas

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2026-02-23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6g7h8"
down_revision: str | None = "b2c3d4e5f6g7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "personas",
        sa.Column("daily_token_budget", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "personas",
        sa.Column("tokens_used_today", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "personas",
        sa.Column("budget_reset_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("personas", "budget_reset_at")
    op.drop_column("personas", "tokens_used_today")
    op.drop_column("personas", "daily_token_budget")
