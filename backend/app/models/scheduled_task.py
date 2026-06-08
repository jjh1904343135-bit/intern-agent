from __future__ import annotations

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AssistantScheduledTask(Base):
    __tablename__ = "assistant_scheduled_tasks"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    source_session_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="SET NULL"), nullable=True)
    assistant_type: Mapped[str] = mapped_column(String(50), nullable=False, server_default="ai_assistant")
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    schedule_type: Mapped[str] = mapped_column(String(20), nullable=False)
    schedule_value: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=func.jsonb_build_object())
    timezone: Mapped[str] = mapped_column(String(80), nullable=False, server_default="Asia/Shanghai")
    next_run_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
    last_run_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="enabled")
    source_channel: Mapped[str] = mapped_column(String(24), nullable=False, server_default="web")
    delivery_channel: Mapped[str] = mapped_column(String(24), nullable=False, server_default="inbox")
    telegram_chat_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    deliver: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    tool_allowlist: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=func.jsonb_build_array())
    task_metadata: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, server_default=func.jsonb_build_object())
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    locked_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now())
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now())


class AssistantScheduledTaskRun(Base):
    __tablename__ = "assistant_scheduled_task_runs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    task_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("assistant_scheduled_tasks.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    started_at: Mapped[str] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now())
    finished_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="running")
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_metadata: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, server_default=func.jsonb_build_object())


class AssistantTaskInbox(Base):
    __tablename__ = "assistant_task_inbox"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), ForeignKey("assistant_scheduled_tasks.id", ondelete="SET NULL"), nullable=True)
    task_run_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), ForeignKey("assistant_scheduled_task_runs.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="unread")
    source_channel: Mapped[str] = mapped_column(String(24), nullable=False, server_default="scheduled_task")
    inbox_metadata: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, server_default=func.jsonb_build_object())
    read_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now())
