from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models.application import Application


class ApplicationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        user_id: str,
        job_id: str,
        resume_id: str,
        source: str = "manual",
        cover_letter: str | None = None,
    ) -> Application:
        now = datetime.now(UTC).replace(tzinfo=None)
        application = Application(
            user_id=user_id,
            job_id=job_id,
            resume_id=resume_id,
            status="saved",
            source=source,
            cover_letter=cover_letter,
            applied_at=now,
            status_updated_at=now,
        )
        self.db.add(application)
        self.db.commit()
        self.db.refresh(application)
        return application

    def get_by_user_and_job(self, *, user_id: str, job_id: str) -> Application | None:
        stmt: Select[tuple[Application]] = select(Application).where(
            Application.user_id == user_id,
            Application.job_id == job_id,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_id(self, *, application_id: str, user_id: str | None = None) -> Application | None:
        stmt: Select[tuple[Application]] = select(Application).where(Application.id == application_id)
        if user_id is not None:
            stmt = stmt.where(Application.user_id == user_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def list_by_user_id(self, *, user_id: str) -> list[Application]:
        stmt: Select[tuple[Application]] = (
            select(Application)
            .where(Application.user_id == user_id)
            .order_by(Application.status_updated_at.desc(), Application.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars())

    def list_by_statuses(self, *, statuses: list[str], limit: int = 10, user_id: str | None = None) -> list[Application]:
        stmt: Select[tuple[Application]] = (
            select(Application)
            .where(Application.status.in_(statuses))
            .order_by(Application.status_updated_at.asc(), Application.created_at.asc())
            .limit(limit)
        )
        if user_id is not None:
            stmt = stmt.where(Application.user_id == user_id)
        return list(self.db.execute(stmt).scalars())

    def advance_status(self, *, application: Application, next_status: str) -> Application:
        application.status = next_status
        application.status_updated_at = datetime.now(UTC).replace(tzinfo=None)
        self.db.add(application)
        self.db.commit()
        self.db.refresh(application)
        return application

    def update_tracking_notes(self, *, application: Application, tracking_notes: dict) -> Application:
        """Persist user-maintained application notes without changing workflow state."""
        application.tracking_notes = tracking_notes
        application.status_updated_at = datetime.now(UTC).replace(tzinfo=None)
        self.db.add(application)
        self.db.commit()
        self.db.refresh(application)
        return application
