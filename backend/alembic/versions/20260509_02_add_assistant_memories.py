"""add assistant memories

Revision ID: 20260509_02
Revises: 20260509_01
Create Date: 2026-05-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260509_02"
down_revision = "20260509_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assistant_type", sa.String(length=50), nullable=False),
        sa.Column("scope_type", sa.String(length=50), nullable=False, server_default="global"),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("memory_kind", sa.String(length=50), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("source", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("assistant_type IN ('ai_assistant', 'interview_assistant')", name="ck_assistant_memories_assistant_type"),
        sa.CheckConstraint("scope_type IN ('global', 'session', 'job', 'resume')", name="ck_assistant_memories_scope_type"),
    )
    op.create_index("ix_assistant_memories_user_assistant", "assistant_memories", ["user_id", "assistant_type"])
    op.create_index("ix_assistant_memories_scope", "assistant_memories", ["scope_type", "scope_id"])
    op.execute(
        """
        CREATE UNIQUE INDEX uq_assistant_memories_identity
        ON assistant_memories (
            user_id,
            assistant_type,
            scope_type,
            COALESCE(scope_id, '00000000-0000-0000-0000-000000000000'::uuid),
            key
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_assistant_memories_identity")
    op.drop_index("ix_assistant_memories_scope", table_name="assistant_memories")
    op.drop_index("ix_assistant_memories_user_assistant", table_name="assistant_memories")
    op.drop_table("assistant_memories")
