from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tool_support import bootstrap_project_paths, emit, fail, ok

TOOL = "backend-service-tool"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="List FastAPI routes and methods.")
    parser.add_argument("--prefix", default="", help="Optional path prefix filter, such as /api/v1/jobs.")
    parser.add_argument("--self-test", action="store_true", help="Emit deterministic sample JSON without app imports.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.self_test:
        emit(ok(TOOL, {"routes": [{"path": "/health", "methods": ["GET"]}], "mode": "self-test"}))
        return 0
    input_payload = {"prefix": args.prefix}
    try:
        bootstrap_project_paths()
        from app.main import app

        routes = []
        for route in app.routes:
            path = getattr(route, "path", "")
            if args.prefix and not path.startswith(args.prefix):
                continue
            methods = sorted(getattr(route, "methods", []) or [])
            routes.append({"path": path, "name": getattr(route, "name", None), "methods": methods})
        emit(ok(TOOL, {"total": len(routes), "routes": routes}, input_payload=input_payload))
        return 0
    except Exception as exc:
        emit(fail(TOOL, exc, input_payload=input_payload))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
