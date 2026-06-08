"""add telegram notification tables

Revision ID: 20260530_01
Revises: 20260521_01
Create Date: 2026-05-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260530_01"
down_revision = "20260521_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telegram_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chat_id", sa.String(length=80), nullable=False),
        sa.Column("username", sa.String(length=120), nullable=True),
        sa.Column("first_name", sa.String(length=120), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=False), nullable=True),
        sa.UniqueConstraint("chat_id", name="uq_telegram_accounts_chat_id"),
    )
    op.create_index("ix_telegram_accounts_user_enabled", "telegram_accounts", ["user_id", "enabled"])

    op.create_table(
        "notification_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("event_key", sa.String(length=200), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("subject_id", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=120), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("decision", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("event_time", sa.DateTime(timezone=False), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_notification_events_user_channel_sent", "notification_events", ["user_id", "channel", "sent_at"])
    op.create_index("ix_notification_events_event_key", "notification_events", ["user_id", "channel", "event_key", "status"])
    op.create_index("ix_notification_events_event_type", "notification_events", ["user_id", "channel", "event_type", "status"])


def downgrade() -> None:
    op.drop_index("ix_notification_events_event_type", table_name="notification_events")
    op.drop_index("ix_notification_events_event_key", table_name="notification_events")
    op.drop_index("ix_notification_events_user_channel_sent", table_name="notification_events")
    op.drop_table("notification_events")
    op.drop_index("ix_telegram_accounts_user_enabled", table_name="telegram_accounts")
    op.drop_table("telegram_accounts")
