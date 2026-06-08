"""Long-term memory records for isolated assistants."""

from __future__ import annotations

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AssistantMemory(Base):
    __tablename__ = "assistant_memories"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    assistant_type: Mapped[str] = mapped_column(String(50), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(50), nullable=False, server_default="global")
    scope_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    memory_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=func.jsonb_build_object())
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.5")
    source: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_ref: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=func.jsonb_build_object())
    created_at: Mapped[str] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now())
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now())
    expires_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
    deleted_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
