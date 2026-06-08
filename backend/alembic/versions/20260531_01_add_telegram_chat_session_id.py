"""add telegram chat session link

Revision ID: 20260531_01
Revises: 20260530_01
Create Date: 2026-05-31
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260531_01"
down_revision = "20260530_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("telegram_accounts", sa.Column("chat_session_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_telegram_accounts_chat_session_id",
        "telegram_accounts",
        "chat_sessions",
        ["chat_session_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_telegram_accounts_chat_session_id", "telegram_accounts", ["chat_session_id"])


def downgrade() -> None:
    op.drop_index("ix_telegram_accounts_chat_session_id", table_name="telegram_accounts")
    op.drop_constraint("fk_telegram_accounts_chat_session_id", "telegram_accounts", type_="foreignkey")
    op.drop_column("telegram_accounts", "chat_session_id")
