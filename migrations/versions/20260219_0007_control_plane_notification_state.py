"""add durable control-plane and notification state tables

Revision ID: 20260219_0007
Revises: 20260216_0006
Create Date: 2026-02-19 22:05:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260219_0007"
down_revision = "20260216_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategy_runtime_state",
        sa.Column("strategy_id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(length=8), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("changed_by", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.CheckConstraint("mode IN ('MOCK','REAL')", name="ck_strategy_runtime_state_mode"),
        sa.CheckConstraint("state IN ('ENABLED','DISABLED','PAUSED')", name="ck_strategy_runtime_state_state"),
    )

    op.create_table(
        "mode_audit_events",
        sa.Column("event_id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("mode", sa.String(length=8), nullable=False),
        sa.Column("changed_by", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("mode IN ('MOCK','REAL')", name="ck_mode_audit_events_mode"),
    )
    op.create_index("idx_mode_audit_events_changed_at", "mode_audit_events", ["changed_at"])

    op.create_table(
        "notification_preferences",
        sa.Column("user_id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("min_severity", sa.String(length=16), nullable=False),
        sa.Column("gateways_json", sa.Text(), nullable=False),
        sa.Column("strategy_ids_json", sa.Text(), nullable=False),
        sa.Column("event_types_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_by", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "min_severity IN ('INFO','WARNING','CRITICAL')",
            name="ck_notification_preferences_min_severity",
        ),
    )

    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("notification_event_id", sa.Text(), nullable=False),
        sa.Column("trace_id", sa.Text(), nullable=False),
        sa.Column("decision_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("gateway", sa.Text(), nullable=False),
        sa.Column("delivery_status", sa.String(length=32), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("logged_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "idx_notification_deliveries_event_time",
        "notification_deliveries",
        ["notification_event_id", "logged_at"],
    )
    op.create_index(
        "idx_notification_deliveries_trace_time",
        "notification_deliveries",
        ["trace_id", "logged_at"],
    )

    op.create_table(
        "notification_trace_spans",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("notification_event_id", sa.Text(), nullable=False),
        sa.Column("trace_id", sa.Text(), nullable=False),
        sa.Column("decision_id", sa.Text(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("latency_ms", sa.Numeric(12, 3), nullable=False, server_default=sa.text("0")),
        sa.Column("gateway", sa.Text(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "idx_notification_trace_spans_trace_time",
        "notification_trace_spans",
        ["trace_id", "completed_at"],
    )
    op.create_index(
        "idx_notification_trace_spans_event_time",
        "notification_trace_spans",
        ["notification_event_id", "completed_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_notification_trace_spans_event_time", table_name="notification_trace_spans")
    op.drop_index("idx_notification_trace_spans_trace_time", table_name="notification_trace_spans")
    op.drop_table("notification_trace_spans")

    op.drop_index("idx_notification_deliveries_trace_time", table_name="notification_deliveries")
    op.drop_index("idx_notification_deliveries_event_time", table_name="notification_deliveries")
    op.drop_table("notification_deliveries")

    op.drop_table("notification_preferences")

    op.drop_index("idx_mode_audit_events_changed_at", table_name="mode_audit_events")
    op.drop_table("mode_audit_events")

    op.drop_table("strategy_runtime_state")
