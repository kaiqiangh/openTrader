"""rename realized_pnl_today to realized_pnl_total

Revision ID: 20260330_0009
Revises: 20260330_0008
Create Date: 2026-03-30 17:00:00
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260330_0009"
down_revision = "20260330_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "portfolio_snapshots", "realized_pnl_today", new_column_name="realized_pnl_total"
    )


def downgrade() -> None:
    op.alter_column(
        "portfolio_snapshots", "realized_pnl_total", new_column_name="realized_pnl_today"
    )
