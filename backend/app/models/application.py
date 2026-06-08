from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    job_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)
    resume_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("resumes.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="saved")
    cover_letter: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
    status_updated_at: Mapped[str] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now())
    interview_date: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
    offer_salary: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    tracking_notes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, server_default="manual")
    created_at: Mapped[str] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now())
