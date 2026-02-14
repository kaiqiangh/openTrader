"""create news schema

Revision ID: 20260214_0005
Revises: 20260214_0004
Create Date: 2026-02-14 12:18:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260214_0005"
down_revision = "20260214_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "news_items",
        sa.Column("news_id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("source_item_id", sa.String(length=128), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("hash", sa.String(length=128), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False, server_default=sa.text("'en'")),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "source",
            "source_item_id",
            name="uq_news_items_source_source_item_id",
        ),
    )
    op.create_index("idx_news_items_published_at", "news_items", ["published_at"])
    op.create_index("idx_news_items_hash", "news_items", ["hash"])

    op.create_table(
        "news_tags",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("news_id", sa.UUID(), sa.ForeignKey("news_items.news_id"), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=True),
        sa.Column("topic", sa.String(length=64), nullable=True),
        sa.Column(
            "relevance_score",
            sa.Numeric(5, 4),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "sentiment_score",
            sa.Numeric(5, 4),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_news_tags_symbol_topic", "news_tags", ["symbol", "topic"])
    op.create_index("idx_news_tags_news_id", "news_tags", ["news_id"])

    op.create_table(
        "news_summaries",
        sa.Column("summary_id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("symbol_scope", sa.String(length=64), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "symbol_scope",
            "window_start",
            "window_end",
            name="uq_news_summaries_scope_window",
        ),
    )
    op.create_index(
        "idx_news_summaries_symbol_scope_window",
        "news_summaries",
        ["symbol_scope", "window_start", "window_end"],
    )

    op.create_table(
        "decision_news_links",
        sa.Column(
            "decision_id",
            sa.UUID(),
            sa.ForeignKey("decision_traces.decision_id"),
            nullable=False,
        ),
        sa.Column(
            "summary_id",
            sa.UUID(),
            sa.ForeignKey("news_summaries.summary_id"),
            nullable=False,
        ),
        sa.Column(
            "news_id",
            sa.UUID(),
            sa.ForeignKey("news_items.news_id"),
            nullable=False,
        ),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint(
            "decision_id",
            "summary_id",
            "news_id",
            name="pk_decision_news_links",
        ),
    )
    op.create_index("idx_decision_news_links_news_id", "decision_news_links", ["news_id"])
    op.create_index("idx_decision_news_links_summary_id", "decision_news_links", ["summary_id"])


def downgrade() -> None:
    op.drop_index("idx_decision_news_links_summary_id", table_name="decision_news_links")
    op.drop_index("idx_decision_news_links_news_id", table_name="decision_news_links")
    op.drop_table("decision_news_links")

    op.drop_index("idx_news_summaries_symbol_scope_window", table_name="news_summaries")
    op.drop_table("news_summaries")

    op.drop_index("idx_news_tags_news_id", table_name="news_tags")
    op.drop_index("idx_news_tags_symbol_topic", table_name="news_tags")
    op.drop_table("news_tags")

    op.drop_index("idx_news_items_hash", table_name="news_items")
    op.drop_index("idx_news_items_published_at", table_name="news_items")
    op.drop_table("news_items")
