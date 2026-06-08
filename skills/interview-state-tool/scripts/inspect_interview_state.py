from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tool_support import bootstrap_project_paths, emit, fail, ok, resolve_user_id

TOOL = "interview-state-tool"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect persisted interview Agent state.")
    parser.add_argument("--session-id", help="Interview session UUID.")
    parser.add_argument("--user-id", help="User UUID, used with --session-id or latest lookup.")
    parser.add_argument("--email", default="admin@example.com", help="User email used when --user-id is absent.")
    parser.add_argument("--self-test", action="store_true", help="Emit deterministic sample JSON without database access.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.self_test:
        emit(ok(TOOL, {"has_agent_state": True, "difficulty": 2, "mode": "self-test"}))
        return 0
    input_payload = {"session_id": args.session_id, "user_id": args.user_id, "email": args.email}
    try:
        bootstrap_project_paths()
        from app.core.database import session_local
        from app.repositories.interview_session_repository import InterviewSessionRepository

        db = session_local()
        try:
            user_id = resolve_user_id(db, user_id=args.user_id, email=args.email)
            repository = InterviewSessionRepository(db)
            session = repository.get_by_id(session_id=args.session_id, user_id=user_id) if args.session_id else None
            if session is None and user_id:
                sessions = repository.list_by_user_id(user_id=user_id, limit=1)
                session = sessions[0] if sessions else None
            if session is None:
                emit(ok(TOOL, {"available": False, "reason": "interview_session_not_found"}, input_payload=input_payload))
                return 0
            report = session.report or {}
            agent_state = report.get("agent_state") or {}
            messages = list(session.messages or [])
            emit(
                ok(
                    TOOL,
                    {
                        "available": True,
                        "session_id": str(session.id),
                        "job_id": str(session.job_id),
                        "resume_id": str(session.resume_id) if session.resume_id else None,
                        "mode": session.mode,
                        "message_count": len(messages),
                        "has_agent_state": bool(agent_state),
                        "difficulty": agent_state.get("difficulty"),
                        "remaining_focus": agent_state.get("remaining_focus") or [],
                        "last_followup_strategy": agent_state.get("last_followup_strategy"),
                        "asked_count": len(agent_state.get("asked_questions") or []),
                        "state_keys": sorted(agent_state.keys()),
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
