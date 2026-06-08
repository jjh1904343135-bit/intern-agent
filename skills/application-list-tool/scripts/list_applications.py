from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tool_support import bootstrap_project_paths, emit, fail, ok, resolve_user_id

TOOL = "application-list-tool"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="List a user's manual application workflow records.")
    parser.add_argument("--user-id", help="User UUID.")
    parser.add_argument("--email", default="admin@example.com", help="User email used when --user-id is absent.")
    parser.add_argument("--limit", type=int, default=10, help="Maximum records to include.")
    parser.add_argument("--self-test", action="store_true", help="Emit deterministic sample JSON without database access.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.self_test:
        emit(ok(TOOL, {"total": 1, "statuses": {"saved": 1}, "mode": "self-test"}))
        return 0
    input_payload = {"user_id": args.user_id, "email": args.email, "limit": args.limit}
    try:
        bootstrap_project_paths()
        from app.core.database import session_local
        from app.repositories.application_repository import ApplicationRepository
        from app.repositories.job_repository import JobRepository
        from app.repositories.resume_repository import ResumeRepository
        from app.services.application_service import ApplicationService

        db = session_local()
        try:
            user_id = resolve_user_id(db, user_id=args.user_id, email=args.email)
            if not user_id:
                emit(ok(TOOL, {"total": 0, "statuses": {}, "items": [], "reason": "user_not_found"}, input_payload=input_payload))
                return 0
            service = ApplicationService(ApplicationRepository(db), JobRepository(db), ResumeRepository(db))
            payload = service.list_applications(user_id=user_id)
            statuses: dict[str, int] = {}
            items = []
            for item in list(payload.get("items") or [])[: max(1, args.limit)]:
                status = item.get("status", "unknown")
                statuses[status] = statuses.get(status, 0) + 1
                items.append(
                    {
                        "application_id": item.get("application_id"),
                        "status": status,
                        "job": item.get("job") or {},
                        "tracking_notes": item.get("tracking_notes") or {},
                    }
                )
            emit(ok(TOOL, {"total": payload.get("total", len(items)), "statuses": statuses, "items": items}, input_payload=input_payload))
            return 0
        finally:
            db.close()
    except Exception as exc:
        emit(fail(TOOL, exc, input_payload=input_payload))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
