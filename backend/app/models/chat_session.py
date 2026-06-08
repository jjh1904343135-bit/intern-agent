from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    messages: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    agent_states: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_agent: Mapped[str | None] = mapped_column(String(50), nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[str] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now())
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now())
