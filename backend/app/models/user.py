from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    # 统一使用 UUID 作为主键，便于后续跨系统扩展。
    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    plan: Mapped[str] = mapped_column(
        Enum("free", "pro", "enterprise", name="user_plan", create_constraint=True),
        nullable=False,
        server_default="free",
    )
    quota_used: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    quota_reset_at: Mapped[str] = mapped_column(DateTime(timezone=False), nullable=False)
    profile: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    onboarding_done: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[str] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now())
    last_active_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
    deleted_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
