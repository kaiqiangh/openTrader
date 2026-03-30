"""create core trading schema

Revision ID: 20260214_0001
Revises: None
Create Date: 2026-02-14 11:26:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260214_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exchanges",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False, unique=True),
        sa.Column("api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("api_secret_encrypted", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "symbols",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("exchange_id", sa.UUID(), sa.ForeignKey("exchanges.id"), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("base_asset", sa.String(length=32), nullable=False),
        sa.Column("quote_asset", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("exchange_id", "symbol", name="uq_symbols_exchange_symbol"),
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("exchange_id", sa.UUID(), sa.ForeignKey("exchanges.id"), nullable=False),
        sa.Column("symbol_id", sa.UUID(), sa.ForeignKey("symbols.id"), nullable=False),
        sa.Column("signal_id", sa.UUID(), nullable=True),
        sa.Column("exchange_order_id", sa.String(length=128), nullable=True),
        sa.Column("client_order_id", sa.String(length=128), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=8), nullable=False),
        sa.Column("price", sa.Numeric(36, 18), nullable=True),
        sa.Column("quantity", sa.Numeric(36, 18), nullable=False),
        sa.Column(
            "filled_quantity", sa.Numeric(36, 18), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("average_price", sa.Numeric(36, 18), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("mode IN ('MOCK','REAL')", name="ck_orders_mode"),
    )

    op.create_table(
        "fills",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("order_id", sa.UUID(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("exchange_fill_id", sa.String(length=128), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("mode", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.Numeric(36, 18), nullable=False),
        sa.Column("price", sa.Numeric(36, 18), nullable=False),
        sa.Column("fee", sa.Numeric(36, 18), nullable=False, server_default=sa.text("0")),
        sa.Column("fee_currency", sa.String(length=16), nullable=True),
        sa.Column(
            "filled_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.CheckConstraint("mode IN ('MOCK','REAL')", name="ck_fills_mode"),
    )

    op.create_table(
        "positions",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("exchange_id", sa.UUID(), sa.ForeignKey("exchanges.id"), nullable=False),
        sa.Column("symbol_id", sa.UUID(), sa.ForeignKey("symbols.id"), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Numeric(36, 18), nullable=False),
        sa.Column("entry_price", sa.Numeric(36, 18), nullable=False),
        sa.Column(
            "unrealized_pnl", sa.Numeric(36, 18), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("realized_pnl", sa.Numeric(36, 18), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "opened_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("snapshot_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mode", sa.String(length=8), nullable=False),
        sa.Column("total_balance_usd", sa.Numeric(36, 18), nullable=False),
        sa.Column("available_balance_usd", sa.Numeric(36, 18), nullable=False),
        sa.Column("locked_balance_usd", sa.Numeric(36, 18), nullable=False),
        sa.Column(
            "unrealized_pnl", sa.Numeric(36, 18), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "realized_pnl_today", sa.Numeric(36, 18), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("mode IN ('MOCK','REAL')", name="ck_portfolio_snapshots_mode"),
    )

    op.create_index(
        "idx_orders_exchange_symbol_status", "orders", ["exchange_id", "symbol_id", "status"]
    )
    op.create_index("idx_fills_order_id", "fills", ["order_id"])
    op.create_index(
        "idx_positions_exchange_symbol_status", "positions", ["exchange_id", "symbol_id", "status"]
    )
    op.create_index(
        "idx_portfolio_snapshots_time_mode", "portfolio_snapshots", ["snapshot_time", "mode"]
    )


def downgrade() -> None:
    op.drop_index("idx_portfolio_snapshots_time_mode", table_name="portfolio_snapshots")
    op.drop_index("idx_positions_exchange_symbol_status", table_name="positions")
    op.drop_index("idx_fills_order_id", table_name="fills")
    op.drop_index("idx_orders_exchange_symbol_status", table_name="orders")

    op.drop_table("portfolio_snapshots")
    op.drop_table("positions")
    op.drop_table("fills")
    op.drop_table("orders")
    op.drop_table("symbols")
    op.drop_table("exchanges")
