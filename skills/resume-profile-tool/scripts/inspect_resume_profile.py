from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tool_support import bootstrap_project_paths, emit, fail, ok, resolve_user_id, trim_list

TOOL = "resume-profile-tool"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect the default or latest resume profile for a user.")
    parser.add_argument("--user-id", help="User UUID.")
    parser.add_argument("--email", default="admin@example.com", help="User email used when --user-id is absent.")
    parser.add_argument("--latest", action="store_true", help="Read latest resume instead of default resume.")
    parser.add_argument("--self-test", action="store_true", help="Emit deterministic sample JSON without database access.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.self_test:
        emit(ok(TOOL, {"available": True, "score": 82, "skills": ["Python"], "mode": "self-test"}))
        return 0
    input_payload = {"user_id": args.user_id, "email": args.email, "latest": args.latest}
    try:
        bootstrap_project_paths()
        from app.core.database import session_local
        from app.repositories.resume_repository import ResumeRepository

        db = session_local()
        try:
            resolved_user_id = resolve_user_id(db, user_id=args.user_id, email=args.email)
            if not resolved_user_id:
                emit(ok(TOOL, {"available": False, "reason": "user_not_found"}, input_payload=input_payload))
                return 0
            repository = ResumeRepository(db)
            resume = repository.get_latest_by_user_id(user_id=resolved_user_id) if args.latest else repository.get_default_by_user_id(user_id=resolved_user_id)
            if resume is None:
                emit(ok(TOOL, {"available": False, "user_id": resolved_user_id, "reason": "resume_not_found"}, input_payload=input_payload))
                return 0
            score = resume.score_report or {}
            parsed = resume.parsed_content or {}
            emit(
                ok(
                    TOOL,
                    {
                        "available": True,
                        "user_id": resolved_user_id,
                        "resume_id": str(resume.id),
                        "file_name": resume.file_name,
                        "parse_status": resume.parse_status,
                        "score": score.get("overall_score"),
                        "rubric_version": score.get("rubric_version"),
                        "risks": trim_list(score.get("risks"), 3),
                        "skills": trim_list(parsed.get("skills"), 8),
                        "dimension_count": len(score.get("dimensions") or []),
                        "has_raw_text": bool(parsed.get("raw_text")),
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
