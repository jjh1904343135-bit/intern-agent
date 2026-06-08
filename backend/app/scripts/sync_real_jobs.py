from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from app.core.database import session_local
from app.models.job import Job
from app.repositories.job_repository import JobRepository
from app.tools.job_discovery import canonicalize_title, infer_job_type
from app.tools.job_sources import FetchFn, JobSourceRecord, default_adapters, default_source_statuses


def sync_real_jobs(fetchers: list[FetchFn] | None = None, *, deactivate_missing: bool = True) -> dict[str, int]:
    records: list[JobSourceRecord] = []
    source_status = default_source_statuses()
    if fetchers is not None:
        for fetcher in fetchers:
            try:
                fetched = fetcher()
                records.extend(fetched)
                source_status["custom"] = {"status": "ok", "reason": None, "records": len(fetched)}
            except Exception as exc:
                source_status["custom"] = {"status": "failed", "reason": str(exc), "records": 0}
    else:
        for adapter in default_adapters():
            status_key = adapter.name.split(":", 1)[0]
            if not adapter.enabled:
                source_status[status_key] = {"status": "disabled", "reason": adapter.disabled_reason, "records": 0}
                continue
            try:
                fetched = adapter.fetch()
                records.extend(fetched)
                previous_records = int(source_status.get(status_key, {}).get("records") or 0)
                source_status[status_key] = {"status": "ok", "reason": None, "records": previous_records + len(fetched)}
            except Exception as exc:
                # A single source should not block the rest of the sync.
                source_status[status_key] = {"status": "failed", "reason": str(exc), "records": 0}

    now = datetime.now(UTC).replace(tzinfo=None)
    records = _dedupe_records(records)
    seen_external_ids = {record.external_id for record in records}
    seen_sources = {record.source for record in records} or {"ashby", "greenhouse"}

    with session_local() as db:
        repository = JobRepository(db)
        synced_jobs: list[Job] = []
        for record in records:
            existing = repository.get_by_external_id(external_id=record.external_id)
            job = existing or Job(id=uuid4(), external_id=record.external_id)
            job.source = record.source
            job.title = record.title
            job.company = record.company
            job.city = record.city
            job.salary_range = record.salary_range
            job.duration = record.duration
            job.jd_text = record.jd_text
            job.apply_url = record.apply_url
            job.deadline = record.deadline
            job.jd_parsed = {
                **(record.metadata or {}),
                "posted_at": record.posted_at.isoformat() if record.posted_at else None,
                "merged_sources": record.metadata.get("merged_sources", [record.source]) if record.metadata else [record.source],
                "source_type": record.metadata.get("source_type", record.source) if record.metadata else record.source,
            }
            job.is_active = True
            job.crawled_at = now
            synced_jobs.append(job)

        repository.save_many(synced_jobs)
        # 即时搜索补抓只追加/更新当前查询结果，不能把同来源其他城市或关键词岗位误下线。
        disabled_jobs = (
            repository.deactivate_missing_by_sources(sources=list(seen_sources), active_external_ids=seen_external_ids)
            if deactivate_missing
            else 0
        )

    return {"synced_jobs": len(synced_jobs), "disabled_jobs": disabled_jobs, "source_status": source_status}


def _dedupe_records(records: list[JobSourceRecord]) -> list[JobSourceRecord]:
    grouped: dict[str, JobSourceRecord] = {}
    for record in records:
        keys = [key for key in [_url_key(record.apply_url), _composite_key(record)] if key]
        if not keys:
            keys = [record.external_id]
        existing_key = next((key for key in keys if key in grouped), None)
        if existing_key is None:
            for key in keys:
                grouped[key] = record
            continue

        existing = grouped[existing_key]
        winner, loser = _choose_record(existing, record)
        merged_sources = sorted(set((winner.metadata or {}).get("merged_sources", [winner.source])) | set((loser.metadata or {}).get("merged_sources", [loser.source])))
        winner.metadata = {**(winner.metadata or {}), "merged_sources": merged_sources, "duplicate_count": len(merged_sources)}
        for key in keys + [_url_key(existing.apply_url), _composite_key(existing)]:
            if key:
                grouped[key] = winner

    unique: dict[str, JobSourceRecord] = {}
    for record in grouped.values():
        unique[record.external_id] = record
    return list(unique.values())


def _choose_record(left: JobSourceRecord, right: JobSourceRecord) -> tuple[JobSourceRecord, JobSourceRecord]:
    left_rank = (_source_priority(left.source), -(len(left.jd_text or "")), left.external_id)
    right_rank = (_source_priority(right.source), -(len(right.jd_text or "")), right.external_id)
    return (left, right) if left_rank <= right_rank else (right, left)


def _source_priority(source: str) -> int:
    priority = {
        "official_company": 0,
        "liepin_mcp": 1,
        "public_board": 1,
        "third_party_search": 2,
        "lever": 3,
        "ashby": 3,
        "greenhouse": 3,
        "seed": 4,
        "market_baseline": 5,
    }
    return priority.get(source, 8)


def _url_key(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlsplit(url)
    significant_query = _significant_url_query(parsed.query)
    cleaned = urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/").lower(), significant_query, ""))
    return f"url:{cleaned}" if cleaned else None

def _composite_key(record: JobSourceRecord) -> str:
    title_key = record.title if (record.metadata or {}).get("live_posting") is True else canonicalize_title(record.title)
    return "|".join(
        [
            _normalize(record.company),
            _normalize(title_key),
            _normalize(record.city or ""),
            infer_job_type(record.title, record.jd_text),
        ]
    )



def _significant_url_query(query: str) -> str:
    identity_keys = {"id", "jobid", "postid", "positionid", "recruitpostid"}
    pairs = [(key, value) for key, value in parse_qsl(query, keep_blank_values=False) if key.lower() in identity_keys]
    return urlencode(sorted(pairs))

def _normalize(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")


if __name__ == "__main__":
    result = sync_real_jobs()
    print(f"synced_jobs={result['synced_jobs']}")
    print(f"disabled_jobs={result['disabled_jobs']}")
