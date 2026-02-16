"""consolidate runtime persistence onto core trading tables

Revision ID: 20260216_0006
Revises: 20260214_0005
Create Date: 2026-02-16 09:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260216_0006"
down_revision = "20260214_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if _table_exists("positions") and not _column_exists("positions", "mode"):
        op.add_column(
            "positions",
            sa.Column("mode", sa.String(length=8), nullable=False, server_default=sa.text("'MOCK'")),
        )
        if not _constraint_exists("positions", "ck_positions_mode"):
            op.create_check_constraint("ck_positions_mode", "positions", "mode IN ('MOCK','REAL')")
        op.alter_column("positions", "mode", server_default=None)
    if _table_exists("positions") and not _index_exists("positions", "idx_positions_mode_symbol"):
        op.create_index("idx_positions_mode_symbol", "positions", ["mode", "symbol_id"])

    if _table_exists("runtime_news_summary_sources") and not _table_exists("news_summary_sources"):
        op.rename_table("runtime_news_summary_sources", "news_summary_sources")
    elif not _table_exists("news_summary_sources"):
        op.create_table(
            "news_summary_sources",
            sa.Column("summary_id", sa.Text(), nullable=False),
            sa.Column("news_id", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.PrimaryKeyConstraint("summary_id", "news_id", name="pk_news_summary_sources"),
        )
    if _table_exists("news_summary_sources") and not _index_exists("news_summary_sources", "idx_news_summary_sources_news_id"):
        op.create_index("idx_news_summary_sources_news_id", "news_summary_sources", ["news_id"])

    for table_name in ("runtime_oms_orders", "runtime_oms_positions", "runtime_oms_portfolio_snapshots"):
        if _table_exists(table_name):
            op.drop_table(table_name)


def downgrade() -> None:
    if _table_exists("positions") and _index_exists("positions", "idx_positions_mode_symbol"):
        op.drop_index("idx_positions_mode_symbol", table_name="positions")

    if _table_exists("news_summary_sources") and _index_exists("news_summary_sources", "idx_news_summary_sources_news_id"):
        op.drop_index("idx_news_summary_sources_news_id", table_name="news_summary_sources")
    if _table_exists("news_summary_sources") and not _table_exists("runtime_news_summary_sources"):
        op.rename_table("news_summary_sources", "runtime_news_summary_sources")

    if not _table_exists("runtime_oms_orders"):
        op.create_table(
            "runtime_oms_orders",
            sa.Column("order_id", sa.Text(), primary_key=True, nullable=False),
            sa.Column("symbol", sa.Text(), nullable=False),
            sa.Column("mode", sa.Text(), nullable=False),
            sa.Column("requested_quantity", sa.Numeric(36, 18), nullable=False),
            sa.Column("status", sa.Text(), nullable=False),
            sa.Column("filled_quantity", sa.Numeric(36, 18), nullable=False),
            sa.Column("average_price", sa.Numeric(36, 18), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
    if not _table_exists("runtime_oms_positions"):
        op.create_table(
            "runtime_oms_positions",
            sa.Column("mode", sa.Text(), nullable=False),
            sa.Column("symbol", sa.Text(), nullable=False),
            sa.Column("quantity", sa.Numeric(36, 18), nullable=False),
            sa.Column("average_entry_price", sa.Numeric(36, 18), nullable=False),
            sa.Column("realized_pnl", sa.Numeric(36, 18), nullable=False),
            sa.Column("status", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.PrimaryKeyConstraint("mode", "symbol", name="pk_runtime_oms_positions"),
        )
    if not _table_exists("runtime_oms_portfolio_snapshots"):
        op.create_table(
            "runtime_oms_portfolio_snapshots",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("snapshot_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("mode", sa.Text(), nullable=False),
            sa.Column("total_balance_usd", sa.Numeric(36, 18), nullable=False),
            sa.Column("available_balance_usd", sa.Numeric(36, 18), nullable=False),
            sa.Column("locked_balance_usd", sa.Numeric(36, 18), nullable=False),
            sa.Column("unrealized_pnl", sa.Numeric(36, 18), nullable=False),
            sa.Column("realized_pnl_today", sa.Numeric(36, 18), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in set(inspector.get_table_names())


def _column_exists(table_name: str, column_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    inspector = sa.inspect(op.get_bind())
    return any(column.get("name") == column_name for column in inspector.get_columns(table_name))


def _constraint_exists(table_name: str, constraint_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    inspector = sa.inspect(op.get_bind())
    return any(item.get("name") == constraint_name for item in inspector.get_check_constraints(table_name))


def _index_exists(table_name: str, index_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    inspector = sa.inspect(op.get_bind())
    return any(index.get("name") == index_name for index in inspector.get_indexes(table_name))

