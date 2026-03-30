"""create agent trace schema

Revision ID: 20260214_0003
Revises: 20260214_0002
Create Date: 2026-02-14 11:45:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260214_0003"
down_revision = "20260214_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "decision_traces",
        sa.Column("decision_id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=False),
        sa.Column("strategy_id", sa.UUID(), nullable=False),
        sa.Column("mode", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("mode IN ('MOCK','REAL')", name="ck_decision_traces_mode"),
    )
    op.create_index("idx_decision_traces_trace_id", "decision_traces", ["trace_id"], unique=True)

    op.create_table(
        "agent_runs",
        sa.Column("agent_run_id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column(
            "decision_id", sa.UUID(), sa.ForeignKey("decision_traces.decision_id"), nullable=False
        ),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("input_ref", sa.String(length=256), nullable=True),
        sa.Column("output_ref", sa.String(length=256), nullable=True),
        sa.Column("latency_ms", sa.Numeric(10, 2), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_agent_runs_decision_id", "agent_runs", ["decision_id"])
    op.create_index(
        "idx_agent_runs_decision_id_agent_name", "agent_runs", ["decision_id", "agent_name"]
    )

    op.create_table(
        "agent_messages",
        sa.Column("message_id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column(
            "agent_run_id", sa.UUID(), sa.ForeignKey("agent_runs.agent_run_id"), nullable=False
        ),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_agent_messages_agent_run_id_created_at",
        "agent_messages",
        ["agent_run_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_agent_messages_agent_run_id_created_at", table_name="agent_messages")
    op.drop_table("agent_messages")

    op.drop_index("idx_agent_runs_decision_id_agent_name", table_name="agent_runs")
    op.drop_index("idx_agent_runs_decision_id", table_name="agent_runs")
    op.drop_table("agent_runs")

    op.drop_index("idx_decision_traces_trace_id", table_name="decision_traces")
    op.drop_table("decision_traces")
