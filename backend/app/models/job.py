from sqlalchemy import Boolean, Date, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    external_id: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    company: Mapped[str] = mapped_column(String(200), nullable=False)
    city: Mapped[str | None] = mapped_column(String(200), nullable=True)
    salary_range: Mapped[str | None] = mapped_column(String(200), nullable=True)
    duration: Mapped[str | None] = mapped_column(String(100), nullable=True)
    jd_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    jd_parsed: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    embedding_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    apply_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    deadline: Mapped[str | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    crawled_at: Mapped[str] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now())
