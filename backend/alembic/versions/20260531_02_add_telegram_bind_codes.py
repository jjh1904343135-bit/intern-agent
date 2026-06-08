"""add telegram bind codes

Revision ID: 20260531_02
Revises: 20260531_01
Create Date: 2026-05-31
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260531_02"
down_revision = "20260531_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telegram_bind_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("code_hash", name="uq_telegram_bind_codes_code_hash"),
    )
    op.create_index("ix_telegram_bind_codes_user_created", "telegram_bind_codes", ["user_id", "created_at"])
    op.create_index("ix_telegram_bind_codes_expires_at", "telegram_bind_codes", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_telegram_bind_codes_expires_at", table_name="telegram_bind_codes")
    op.drop_index("ix_telegram_bind_codes_user_created", table_name="telegram_bind_codes")
    op.drop_table("telegram_bind_codes")
