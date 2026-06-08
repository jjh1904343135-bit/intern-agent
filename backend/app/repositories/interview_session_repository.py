from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.interview_session import InterviewSession


class InterviewSessionRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, *, user_id: str, job_id: str, resume_id: str | None, mode: str, messages: list[dict]) -> InterviewSession:
        session = InterviewSession(
            user_id=user_id,
            job_id=job_id,
            resume_id=resume_id,
            mode=mode,
            messages=messages,
            report=None,
            duration_min=None,
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_by_id(self, *, session_id: str, user_id: str | None = None) -> InterviewSession | None:
        stmt: Select[tuple[InterviewSession]] = select(InterviewSession).where(InterviewSession.id == session_id)
        if user_id is not None:
            stmt = stmt.where(InterviewSession.user_id == user_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_latest_by_user_job_resume_mode(
        self,
        *,
        user_id: str,
        job_id: str,
        resume_id: str,
        mode: str,
    ) -> InterviewSession | None:
        stmt: Select[tuple[InterviewSession]] = (
            select(InterviewSession)
            .where(
                InterviewSession.user_id == user_id,
                InterviewSession.job_id == job_id,
                InterviewSession.resume_id == resume_id,
                InterviewSession.mode == mode,
            )
            .order_by(InterviewSession.started_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_by_user_id(self, *, user_id: str, limit: int = 5) -> list[InterviewSession]:
        stmt: Select[tuple[InterviewSession]] = (
            select(InterviewSession)
            .where(InterviewSession.user_id == user_id)
            .order_by(InterviewSession.started_at.desc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars())

    def count_by_user_id(self, *, user_id: str) -> int:
        stmt = select(func.count()).select_from(InterviewSession).where(InterviewSession.user_id == user_id)
        return int(self.db.execute(stmt).scalar_one())

    def save_messages(self, *, session: InterviewSession, messages: list[dict]) -> InterviewSession:
        session.messages = messages
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def save_report(self, *, session: InterviewSession, report: dict) -> InterviewSession:
        session.report = report
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session
