"""create llm governance schema

Revision ID: 20260214_0004
Revises: 20260214_0003
Create Date: 2026-02-14 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260214_0004"
down_revision = "20260214_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_calls",
        sa.Column("llm_call_id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=False),
        sa.Column("decision_id", sa.UUID(), nullable=False),
        sa.Column("strategy_id", sa.UUID(), nullable=False),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_payload", sa.JSON(), nullable=False),
        sa.Column("response_payload", sa.JSON(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("latency_ms", sa.Numeric(10, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("estimated_cost", sa.Numeric(18, 8), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_llm_calls_trace_id", "llm_calls", ["trace_id"])
    op.create_index(
        "idx_llm_calls_strategy_agent_created_at",
        "llm_calls",
        ["strategy_id", "agent_name", "created_at"],
    )

    op.create_table(
        "llm_usage_daily",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("strategy_id", sa.UUID(), nullable=False),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("estimated_cost", sa.Numeric(18, 8), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("strategy_id", "agent_name", "date", name="uq_llm_usage_daily_scope"),
    )

    op.create_table(
        "llm_usage_monthly",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("strategy_id", sa.UUID(), nullable=False),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("month", sa.String(length=7), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("estimated_cost", sa.Numeric(18, 8), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "strategy_id", "agent_name", "month", name="uq_llm_usage_monthly_scope"
        ),
    )

    op.create_table(
        "llm_quota_limits",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("strategy_id", sa.UUID(), nullable=False),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("daily_token_limit", sa.Integer(), nullable=False),
        sa.Column("monthly_cost_limit", sa.Numeric(18, 8), nullable=False),
        sa.Column("is_hard_limit", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("strategy_id", "agent_name", name="uq_llm_quota_limits_scope"),
    )


def downgrade() -> None:
    op.drop_table("llm_quota_limits")
    op.drop_table("llm_usage_monthly")
    op.drop_table("llm_usage_daily")

    op.drop_index("idx_llm_calls_strategy_agent_created_at", table_name="llm_calls")
    op.drop_index("idx_llm_calls_trace_id", table_name="llm_calls")
    op.drop_table("llm_calls")
