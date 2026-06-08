from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tool_support import bootstrap_project_paths, emit, fail, ok, resolve_user_id, safe_memory_item

TOOL = "assistant-memory-tool"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect isolated long-term assistant memories.")
    parser.add_argument("--user-id", help="User UUID.")
    parser.add_argument("--email", default="admin@example.com", help="User email used when --user-id is absent.")
    parser.add_argument("--assistant-type", default="ai_assistant", choices=["ai_assistant", "interview_assistant"], help="Memory partition.")
    parser.add_argument("--scope-type", help="Optional scope filter.")
    parser.add_argument("--scope-id", help="Optional scope UUID.")
    parser.add_argument("--limit", type=int, default=12, help="Maximum memories.")
    parser.add_argument("--include-pending", action="store_true", help="Include hidden pending candidates for debugging.")
    parser.add_argument("--self-test", action="store_true", help="Emit deterministic sample JSON without database access.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.self_test:
        emit(ok(TOOL, {"assistant_type": "ai_assistant", "count": 1, "mode": "self-test"}))
        return 0
    input_payload = {
        "user_id": args.user_id,
        "email": args.email,
        "assistant_type": args.assistant_type,
        "scope_type": args.scope_type,
        "scope_id": args.scope_id,
        "limit": args.limit,
        "include_pending": args.include_pending,
    }
    try:
        bootstrap_project_paths()
        from app.core.database import session_local
        from app.repositories.assistant_memory_repository import AssistantMemoryRepository

        db = session_local()
        try:
            user_id = resolve_user_id(db, user_id=args.user_id, email=args.email)
            if not user_id:
                emit(ok(TOOL, {"assistant_type": args.assistant_type, "count": 0, "items": [], "reason": "user_not_found"}, input_payload=input_payload))
                return 0
            memories = AssistantMemoryRepository(db).list_active(
                user_id=user_id,
                assistant_type=args.assistant_type,
                scope_type=args.scope_type,
                scope_id=args.scope_id,
                limit=args.limit,
                include_pending=args.include_pending,
            )
            emit(
                ok(
                    TOOL,
                    {"assistant_type": args.assistant_type, "count": len(memories), "items": [safe_memory_item(item) for item in memories]},
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
