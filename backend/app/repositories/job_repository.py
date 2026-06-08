from __future__ import annotations

import re
from datetime import date

from datetime import UTC, datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models.job import Job


class JobRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_active_jobs(self, *, keyword: str | None = None) -> list[Job]:
        real_count_stmt = select(func.count()).select_from(Job).where(Job.is_active.is_(True), Job.source != "mock")
        has_real_jobs = int(self.db.execute(real_count_stmt).scalar_one()) > 0
        stmt: Select[tuple[Job]] = (
            select(Job)
            .where(Job.is_active.is_(True))
            .where(or_(Job.apply_url.is_(None), ~Job.apply_url.ilike("%example.com%")))
            .order_by(Job.deadline.asc().nullslast(), Job.crawled_at.desc())
        )
        if has_real_jobs:
            stmt = stmt.where(Job.source != "mock")
        for token in _split_search_tokens(keyword):
            pattern = f"%{token}%"
            # 多词查询按 AND 处理，支持“腾讯Java”拆成公司 + 岗位词。
            stmt = stmt.where(
                or_(
                    Job.title.ilike(pattern),
                    Job.company.ilike(pattern),
                    Job.city.ilike(pattern),
                    Job.jd_text.ilike(pattern),
                )
            )
        return list(self.db.execute(stmt).scalars())

    def create_many(self, jobs: list[Job]) -> None:
        self.db.add_all(jobs)
        self.db.commit()

    def save_many(self, jobs: list[Job]) -> None:
        if not jobs:
            return
        self.db.add_all(jobs)
        self.db.commit()

    def get_by_id(self, *, job_id: str) -> Job | None:
        stmt: Select[tuple[Job]] = select(Job).where(Job.id == job_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_external_id(self, *, external_id: str) -> Job | None:
        stmt: Select[tuple[Job]] = select(Job).where(Job.external_id == external_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_ids(self, job_ids: list[str]) -> list[Job]:
        if not job_ids:
            return []
        stmt: Select[tuple[Job]] = select(Job).where(Job.id.in_(job_ids))
        jobs = list(self.db.execute(stmt).scalars())
        sort_map = {job_id: index for index, job_id in enumerate(job_ids)}
        jobs.sort(key=lambda item: sort_map.get(str(item.id), 10**9))
        return jobs

    def upsert_embedding_id(self, *, job: Job, embedding_id: str) -> None:
        job.embedding_id = embedding_id
        self.db.add(job)
        self.db.commit()

    def exists_by_external_id(self, external_id: str) -> bool:
        stmt = select(Job.id).where(Job.external_id == external_id)
        return self.db.execute(stmt).first() is not None

    def deactivate_missing_by_sources(self, *, sources: list[str], active_external_ids: set[str]) -> int:
        if not sources:
            return 0
        stmt: Select[tuple[Job]] = select(Job).where(Job.source.in_(sources), Job.is_active.is_(True))
        jobs = list(self.db.execute(stmt).scalars())
        disabled = 0
        now = datetime.now(UTC).replace(tzinfo=None)
        for job in jobs:
            if job.external_id in active_external_ids:
                continue
            job.is_active = False
            job.crawled_at = now
            self.db.add(job)
            disabled += 1
        self.db.commit()
        return disabled


def _split_search_tokens(keyword: str | None) -> list[str]:
    """Split mixed Chinese/English search text without breaking Chinese job titles into single chars."""
    normalized = (keyword or "").strip()
    if not normalized:
        return []
    tokens = re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+", normalized)
    return [token for token in tokens if token.strip()]
