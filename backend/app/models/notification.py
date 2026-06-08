from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TelegramAccount(Base):
    __tablename__ = "telegram_accounts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    chat_session_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    chat_id: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    username: Mapped[str | None] = mapped_column(String(120), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[str] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now())
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now())
    last_seen_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)


class NotificationEvent(Base):
    __tablename__ = "notification_events"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    event_key: Mapped[str] = mapped_column(String(200), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    subject_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=func.jsonb_build_object())
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=func.jsonb_build_object())
    event_time: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
    sent_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now())


class TelegramBindCode(Base):
    __tablename__ = "telegram_bind_codes"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    expires_at: Mapped[str] = mapped_column(DateTime(timezone=False), nullable=False)
    used_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now())
