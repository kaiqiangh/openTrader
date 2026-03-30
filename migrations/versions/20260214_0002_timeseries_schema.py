"""create timeseries schema and hypertables

Revision ID: 20260214_0002
Revises: 20260214_0001
Create Date: 2026-02-14 11:27:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260214_0002"
down_revision = "20260214_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    op.create_table(
        "klines",
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exchange", sa.String(length=50), nullable=False),
        sa.Column("symbol", sa.String(length=50), nullable=False),
        sa.Column("interval", sa.String(length=10), nullable=False),
        sa.Column("open", sa.Numeric(36, 18), nullable=False),
        sa.Column("high", sa.Numeric(36, 18), nullable=False),
        sa.Column("low", sa.Numeric(36, 18), nullable=False),
        sa.Column("close", sa.Numeric(36, 18), nullable=False),
        sa.Column("volume", sa.Numeric(36, 18), nullable=False),
        sa.Column("quote_volume", sa.Numeric(36, 18), nullable=False),
        sa.Column("trades", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.PrimaryKeyConstraint("time", "exchange", "symbol", "interval", name="pk_klines"),
    )

    op.create_table(
        "orderbook_snapshots",
        sa.Column("snapshot_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exchange", sa.String(length=50), nullable=False),
        sa.Column("symbol", sa.String(length=50), nullable=False),
        sa.Column("bids", sa.JSON(), nullable=False),
        sa.Column("asks", sa.JSON(), nullable=False),
        sa.Column("best_bid", sa.Numeric(36, 18), nullable=False),
        sa.Column("best_ask", sa.Numeric(36, 18), nullable=False),
        sa.Column("spread_bps", sa.Numeric(10, 4), nullable=False),
        sa.PrimaryKeyConstraint(
            "snapshot_time", "exchange", "symbol", name="pk_orderbook_snapshots"
        ),
    )

    op.create_index("idx_klines_lookup", "klines", ["exchange", "symbol", "interval", "time"])
    op.create_index(
        "idx_orderbook_snapshots_lookup",
        "orderbook_snapshots",
        ["exchange", "symbol", "snapshot_time"],
    )

    op.execute(
        "SELECT create_hypertable('klines', 'time', if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 day')"
    )
    op.execute(
        "SELECT create_hypertable('orderbook_snapshots', 'snapshot_time', if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 hour')"
    )


def downgrade() -> None:
    op.drop_index("idx_orderbook_snapshots_lookup", table_name="orderbook_snapshots")
    op.drop_index("idx_klines_lookup", table_name="klines")

    op.drop_table("orderbook_snapshots")
    op.drop_table("klines")
