"""add agent memories

Revision ID: 20260419_01
Revises: 20260406_01
Create Date: 2026-04-19 18:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260419_01"
down_revision: Union[str, Sequence[str], None] = "20260406_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """中文注释：用于处理 upgrade 相关后端功能。"""
    op.create_table(
        "agent_memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "key", name="uq_agent_memories_user_key"),
    )


def downgrade() -> None:
    """中文注释：用于处理 downgrade 相关后端功能。"""
    op.drop_table("agent_memories")
