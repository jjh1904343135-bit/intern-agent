from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tool_support import bootstrap_project_paths, emit, fail, ok, resolve_user_id

TOOL = "assistant-memory-tool"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export assistant long-term memory as a Markdown runtime snapshot.")
    parser.add_argument("--user-id", help="User UUID.")
    parser.add_argument("--email", default="admin@example.com", help="User email used when --user-id is absent.")
    parser.add_argument("--assistant-type", default="ai_assistant", choices=["ai_assistant", "interview_assistant"], help="Memory partition.")
    parser.add_argument("--runtime-root", default="/app/runtime", help="Runtime root containing memory/users snapshots.")
    parser.add_argument("--include-pending", action="store_true", help="Include pending candidates in the source query.")
    parser.add_argument("--self-test", action="store_true", help="Emit deterministic sample JSON without database access.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.self_test:
        emit(
            ok(
                TOOL,
                {
                    "assistant_type": "ai_assistant",
                    "available": True,
                    "path": "/app/runtime/memory/users/11111111-1111-1111-1111-111111111111/ai_assistant.md",
                    "item_count": 1,
                    "char_count": 128,
                    "mode": "self-test",
                },
            )
        )
        return 0

    input_payload = {
        "user_id": args.user_id,
        "email": args.email,
        "assistant_type": args.assistant_type,
        "runtime_root": args.runtime_root,
        "include_pending": args.include_pending,
    }
    try:
        bootstrap_project_paths()
        from app.core.database import session_local
        from app.services.assistant_memory_markdown_service import AssistantMemoryMarkdownService

        db = session_local()
        try:
            user_id = resolve_user_id(db, user_id=args.user_id, email=args.email)
            if not user_id:
                emit(
                    ok(
                        TOOL,
                        {
                            "assistant_type": args.assistant_type,
                            "available": False,
                            "path": None,
                            "item_count": 0,
                            "char_count": 0,
                            "reason": "user_not_found",
                        },
                        input_payload=input_payload,
                    )
                )
                return 0
            snapshot = AssistantMemoryMarkdownService(runtime_root=args.runtime_root).export_snapshot(
                db=db,
                user_id=user_id,
                assistant_type=args.assistant_type,
                include_pending=args.include_pending,
            )
            snapshot.pop("content", None)
            emit(ok(TOOL, snapshot, input_payload=input_payload))
            return 0
        finally:
            db.close()
    except Exception as exc:
        emit(fail(TOOL, exc, input_payload=input_payload))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
