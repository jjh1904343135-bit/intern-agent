from sqlalchemy import DateTime, Enum, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    job_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)
    resume_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), ForeignKey("resumes.id"), nullable=True)
    mode: Mapped[str] = mapped_column(
        Enum("standard", "pressure", "case", "negotiation", name="interview_mode", create_constraint=True),
        nullable=False,
    )
    messages: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[str] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now())
    ended_at: Mapped[str | None] = mapped_column(DateTime(timezone=False), nullable=True)
