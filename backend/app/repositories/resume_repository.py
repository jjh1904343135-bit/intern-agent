from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.resume import Resume


class ResumeRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        user_id: str,
        file_url: str,
        file_name: str,
        parse_status: str,
    ) -> Resume:
        resume = Resume(
            user_id=user_id,
            file_url=file_url,
            file_name=file_name,
            parse_status=parse_status,
        )
        self.db.add(resume)
        self.db.commit()
        self.db.refresh(resume)
        return resume

    def get_by_id(self, *, resume_id: str, user_id: str | None = None) -> Resume | None:
        stmt: Select[tuple[Resume]] = select(Resume).where(Resume.id == resume_id)
        if user_id is not None:
            stmt = stmt.where(Resume.user_id == user_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_default_by_user_id(self, *, user_id: str) -> Resume | None:
        stmt: Select[tuple[Resume]] = (
            select(Resume)
            .where(Resume.user_id == user_id, Resume.is_default.is_(True))
            .order_by(Resume.updated_at.desc())
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_latest_by_user_id(self, *, user_id: str) -> Resume | None:
        stmt: Select[tuple[Resume]] = select(Resume).where(Resume.user_id == user_id).order_by(Resume.updated_at.desc())
        return self.db.execute(stmt).scalar_one_or_none()

    def count_by_user_id(self, *, user_id: str) -> int:
        stmt = select(func.count()).select_from(Resume).where(Resume.user_id == user_id)
        return int(self.db.execute(stmt).scalar_one())

    def list_processing(self, *, limit: int = 10) -> list[Resume]:
        stmt = (
            select(Resume)
            .where(Resume.parse_status == "processing")
            .order_by(Resume.created_at.asc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars())

    def mark_done(self, *, resume: Resume, parsed_content: dict, score_report: dict | None = None) -> Resume:
        now = datetime.now(UTC).replace(tzinfo=None)
        self.db.query(Resume).filter(Resume.user_id == resume.user_id).update({Resume.is_default: False})
        resume.parse_status = "done"
        resume.parsed_content = parsed_content
        resume.parse_error = None
        resume.score_report = score_report
        resume.is_default = True
        resume.updated_at = now
        self.db.add(resume)
        self.db.commit()
        self.db.refresh(resume)
        return resume

    def save_parsed_content_progress(self, *, resume: Resume, parsed_content: dict) -> Resume:
        """Save structured content before scoring so clients can show the scoring stage."""
        resume.parse_status = "processing"
        resume.parsed_content = parsed_content
        resume.updated_at = datetime.now(UTC).replace(tzinfo=None)
        self.db.add(resume)
        self.db.commit()
        self.db.refresh(resume)
        return resume

    def mark_failed(self, *, resume: Resume, parse_error: str) -> Resume:
        resume.parse_status = "failed"
        resume.parse_error = parse_error
        resume.updated_at = datetime.now(UTC).replace(tzinfo=None)
        self.db.add(resume)
        self.db.commit()
        self.db.refresh(resume)
        return resume

    def save_score_report(self, *, resume: Resume, score_report: dict) -> Resume:
        resume.score_report = score_report
        resume.updated_at = datetime.now(UTC).replace(tzinfo=None)
        self.db.add(resume)
        self.db.commit()
        self.db.refresh(resume)
        return resume
