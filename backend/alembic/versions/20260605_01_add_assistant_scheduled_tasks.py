"""add assistant scheduled tasks

Revision ID: 20260605_01
Revises: 20260531_02
Create Date: 2026-06-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260605_01"
down_revision = "20260531_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_scheduled_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chat_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assistant_type", sa.String(length=50), nullable=False, server_default="ai_assistant"),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("schedule_type", sa.String(length=20), nullable=False),
        sa.Column("schedule_value", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("timezone", sa.String(length=80), nullable=False, server_default="Asia/Shanghai"),
        sa.Column("next_run_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="enabled"),
        sa.Column("source_channel", sa.String(length=24), nullable=False, server_default="web"),
        sa.Column("delivery_channel", sa.String(length=24), nullable=False, server_default="inbox"),
        sa.Column("telegram_chat_id", sa.String(length=80), nullable=True),
        sa.Column("deliver", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("tool_allowlist", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_assistant_scheduled_tasks_user_status", "assistant_scheduled_tasks", ["user_id", "status"])
    op.create_index("ix_assistant_scheduled_tasks_due", "assistant_scheduled_tasks", ["status", "next_run_at"])

    op.create_table(
        "assistant_scheduled_task_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assistant_scheduled_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="running"),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_assistant_scheduled_task_runs_task_started", "assistant_scheduled_task_runs", ["task_id", "started_at"])

    op.create_table(
        "assistant_task_inbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assistant_scheduled_tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("task_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assistant_scheduled_task_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="unread"),
        sa.Column("source_channel", sa.String(length=24), nullable=False, server_default="scheduled_task"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("read_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_assistant_task_inbox_user_status", "assistant_task_inbox", ["user_id", "status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_assistant_task_inbox_user_status", table_name="assistant_task_inbox")
    op.drop_table("assistant_task_inbox")
    op.drop_index("ix_assistant_scheduled_task_runs_task_started", table_name="assistant_scheduled_task_runs")
    op.drop_table("assistant_scheduled_task_runs")
    op.drop_index("ix_assistant_scheduled_tasks_due", table_name="assistant_scheduled_tasks")
    op.drop_index("ix_assistant_scheduled_tasks_user_status", table_name="assistant_scheduled_tasks")
    op.drop_table("assistant_scheduled_tasks")
