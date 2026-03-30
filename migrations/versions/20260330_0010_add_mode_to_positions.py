"""add mode column to positions (idempotent guard)

Revision ID: 20260330_0010
Revises: 20260330_0009
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260330_0010"
down_revision = "20260330_0009"
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


def downgrade() -> None:
    if _table_exists("positions") and _index_exists("positions", "idx_positions_mode_symbol"):
        op.drop_index("idx_positions_mode_symbol", table_name="positions")
    if _table_exists("positions") and _column_exists("positions", "mode"):
        op.drop_column("positions", "mode")


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
