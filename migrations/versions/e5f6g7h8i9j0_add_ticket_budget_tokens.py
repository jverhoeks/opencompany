"""add budget_tokens column to tickets

Revision ID: e5f6g7h8i9j0
Revises: d4e5f6g7h8i9
Create Date: 2026-03-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6g7h8i9j0"
down_revision: str = "d4e5f6g7h8i9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tickets",
        sa.Column("budget_tokens", sa.Integer(), nullable=False, server_default="4000"),
    )


def downgrade() -> None:
    op.drop_column("tickets", "budget_tokens")
