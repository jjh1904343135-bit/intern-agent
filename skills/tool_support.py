from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def bootstrap_project_paths() -> Path:
    skills_root = Path(__file__).resolve().parent
    project_root = skills_root.parent
    backend_root = project_root / "backend"
    for path in (project_root, backend_root):
        path_text = str(path)
        if path.exists() and path_text not in sys.path:
            sys.path.insert(0, path_text)
    return project_root


def compact_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)


def emit(payload: dict[str, Any]) -> None:
    print(compact_json(payload))


def ok(tool: str, result: dict[str, Any], *, input_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": True, "tool": tool, "result": result}
    if input_payload is not None:
        payload["input"] = input_payload
    return payload


def fail(tool: str, error: Exception | str, *, code: str = "tool_error", input_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "tool": tool, "code": code, "error": str(error)}
    if input_payload is not None:
        payload["input"] = input_payload
    return payload


def resolve_user_id(db: Any, *, user_id: str | None = None, email: str | None = None) -> str | None:
    if user_id:
        return user_id
    if not email:
        return None
    from app.repositories.user_repository import UserRepository

    user = UserRepository(db).get_by_email(email)
    return str(user.id) if user is not None else None


def trim_list(values: Any, limit: int) -> list[Any]:
    if not isinstance(values, list):
        return []
    return values[: max(0, limit)]


def safe_memory_item(memory: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": memory.get("key"),
        "memory_kind": memory.get("memory_kind"),
        "scope_type": memory.get("scope_type"),
        "scope_id": memory.get("scope_id"),
        "summary": memory.get("summary"),
        "confidence": memory.get("confidence"),
        "source": memory.get("source"),
        "source_ref": memory.get("source_ref") or {},
    }
