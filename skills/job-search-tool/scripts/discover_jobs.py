from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tool_support import bootstrap_project_paths, emit, fail, ok, resolve_user_id

TOOL = "job-search-tool"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run InternAgent job discovery and recommendation.")
    parser.add_argument("--user-id", help="Optional user UUID for resume-aware scoring.")
    parser.add_argument("--email", help="Optional user email for resume-aware scoring.")
    parser.add_argument("--keyword", help="Role keyword, such as Java or 产品.")
    parser.add_argument("--city", help="City filter.")
    parser.add_argument("--experience", help="Experience filter, such as intern.")
    parser.add_argument("--skills", default="", help="Comma-separated skill filters.")
    parser.add_argument("--limit", type=int, default=8, help="Maximum jobs to return.")
    parser.add_argument("--self-test", action="store_true", help="Emit deterministic sample JSON without database access.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.self_test:
        emit(ok(TOOL, {"total": 1, "jobs": [{"canonical_title": "后端开发实习生"}], "mode": "self-test"}))
        return 0
    input_payload = {key: getattr(args, key) for key in ("user_id", "email", "keyword", "city", "experience", "skills", "limit")}
    try:
        bootstrap_project_paths()
        from app.core.database import session_local
        from app.repositories.job_repository import JobRepository
        from app.repositories.resume_repository import ResumeRepository
        from app.services.job_service import JobService

        skills = tuple(item.strip() for item in args.skills.split(",") if item.strip())
        db = session_local()
        try:
            user_id = resolve_user_id(db, user_id=args.user_id, email=args.email)
            service = JobService(JobRepository(db), ResumeRepository(db))
            payload = service.discover_jobs(user_id=user_id, keyword=args.keyword, city=args.city, experience=args.experience, skills=skills)
            jobs = []
            for job in list(payload.get("jobs") or [])[: max(1, args.limit)]:
                jobs.append(
                    {
                        "id": str(job.get("id") or job.get("job_id") or ""),
                        "raw_title": job.get("raw_title") or job.get("title"),
                        "canonical_title": job.get("canonical_title"),
                        "company": job.get("company"),
                        "city": job.get("city"),
                        "source": job.get("source"),
                        "url": job.get("url") or job.get("apply_url"),
                        "recommendation_score": job.get("recommendation_score"),
                        "matched_skills": job.get("matched_skills") or [],
                        "missing_skills": job.get("missing_skills") or [],
                        "application_priority": job.get("application_priority"),
                    }
                )
            emit(
                ok(
                    TOOL,
                    {
                        "total": payload.get("total", len(jobs)),
                        "source_kind": payload.get("source_kind"),
                        "fallback_notice": payload.get("fallback_notice"),
                        "query_expansions": payload.get("query_expansions") or [],
                        "jobs": jobs,
                    },
                    input_payload=input_payload,
                )
            )
            return 0
        finally:
            db.close()
    except Exception as exc:
        emit(fail(TOOL, exc, input_payload=input_payload))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
