"""add notification_events and notification_delivery_dlq tables

Revision ID: 20260330_0008
Revises: 20260219_0007
Create Date: 2026-03-30 09:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260330_0008"
down_revision = "20260219_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_events",
        sa.Column("notification_event_id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("trace_id", sa.Text(), nullable=True),
        sa.Column("decision_id", sa.Text(), nullable=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column(
            "emitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "severity IN ('INFO','WARNING','CRITICAL')",
            name="ck_notification_events_severity",
        ),
    )
    op.create_index(
        "idx_notification_events_emitted_at",
        "notification_events",
        ["emitted_at"],
    )
    op.create_index(
        "idx_notification_events_type_severity",
        "notification_events",
        ["event_type", "severity"],
    )
    op.create_index(
        "idx_notification_events_idempotency",
        "notification_events",
        ["idempotency_key"],
    )

    op.create_table(
        "notification_delivery_dlq",
        sa.Column("dlq_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("notification_event_id", sa.Text(), nullable=False),
        sa.Column("gateway", sa.Text(), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "moved_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    )
    op.create_index(
        "idx_notification_dlq_event_id",
        "notification_delivery_dlq",
        ["notification_event_id"],
    )
    op.create_index(
        "idx_notification_dlq_moved_at",
        "notification_delivery_dlq",
        ["moved_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_notification_dlq_moved_at", table_name="notification_delivery_dlq")
    op.drop_index("idx_notification_dlq_event_id", table_name="notification_delivery_dlq")
    op.drop_table("notification_delivery_dlq")

    op.drop_index("idx_notification_events_idempotency", table_name="notification_events")
    op.drop_index("idx_notification_events_type_severity", table_name="notification_events")
    op.drop_index("idx_notification_events_emitted_at", table_name="notification_events")
    op.drop_table("notification_events")
