"""Markdown snapshots for assistant long-term memory."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


ALLOWED_ASSISTANT_TYPES = {"ai_assistant", "interview_assistant"}
SNAPSHOT_VERSION = "memory_snapshot_v1"
DEFAULT_RUNTIME_ROOT = Path("/app/runtime")


class AssistantMemoryMarkdownService:
    def __init__(self, *, runtime_root: str | Path = DEFAULT_RUNTIME_ROOT, item_limit: int = 20):
        self.runtime_root = Path(runtime_root)
        self.item_limit = max(1, item_limit)

    def snapshot_path(self, *, user_id: str, assistant_type: str) -> Path:
        safe_user_id = self._validate_user_id(user_id)
        safe_assistant_type = self._validate_assistant_type(assistant_type)
        base = (self.runtime_root / "memory" / "users").resolve()
        path = (base / safe_user_id / f"{safe_assistant_type}.md").resolve()
        if not path.is_relative_to(base):
            raise ValueError("memory snapshot path escaped runtime root")
        return path

    def format_snapshot(
        self,
        *,
        user_id: str,
        assistant_type: str,
        memories: list[dict[str, Any]],
        generated_at: datetime | None = None,
    ) -> str:
        safe_user_id = self._validate_user_id(user_id)
        safe_assistant_type = self._validate_assistant_type(assistant_type)
        timestamp = (generated_at or datetime.now(timezone.utc)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        safe_memories = self._safe_memories(memories)
        lines = [
            "---",
            f"version: {SNAPSHOT_VERSION}",
            f'user_id: "{safe_user_id}"',
            f'assistant_type: "{safe_assistant_type}"',
            f'generated_at: "{timestamp}"',
            'source: "assistant_memories"',
            f"count: {len(safe_memories)}",
            "---",
            "",
            "# Long-Term Memory",
            "",
        ]
        if not safe_memories:
            lines.extend(["No active long-term memories.", ""])
            return "\n".join(lines)

        current_scope: str | None = None
        for memory in safe_memories:
            scope = self._clean_token(memory.get("scope_type") or "global")
            if scope != current_scope:
                lines.extend([f"## {scope.title()}", ""])
                current_scope = scope
            label = f"{self._clean_token(memory.get('memory_kind') or 'memory')}:{self._clean_token(memory.get('key') or 'memory')}"
            confidence = self._format_confidence(memory.get("confidence"))
            source = self._clean_token(memory.get("source") or "unknown")
            summary = self._clean_summary(memory.get("summary") or "")
            lines.extend(
                [
                    f"- `{label}` confidence={confidence} source={source}",
                    f"  {summary or 'No summary available.'}",
                    "",
                ]
            )
        return "\n".join(lines)

    def write_snapshot(self, *, user_id: str, assistant_type: str, memories: list[dict[str, Any]]) -> dict[str, Any]:
        markdown = self.format_snapshot(user_id=user_id, assistant_type=assistant_type, memories=memories)
        path = self.snapshot_path(user_id=user_id, assistant_type=assistant_type)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8")
        return self._snapshot_metadata(path=path, assistant_type=assistant_type, item_count=len(self._safe_memories(memories)), content=markdown)

    def read_snapshot(self, *, user_id: str, assistant_type: str) -> dict[str, Any]:
        path = self.snapshot_path(user_id=user_id, assistant_type=assistant_type)
        if not path.exists():
            return {
                "available": False,
                "assistant_type": self._validate_assistant_type(assistant_type),
                "path": path.as_posix(),
                "item_count": 0,
                "char_count": 0,
                "content": "",
            }
        content = path.read_text(encoding="utf-8")
        item_count = sum(1 for line in content.splitlines() if line.startswith("- `"))
        return self._snapshot_metadata(path=path, assistant_type=assistant_type, item_count=item_count, content=content)

    def export_snapshot(self, *, db: "Session", user_id: str, assistant_type: str, include_pending: bool = False) -> dict[str, Any]:
        from app.repositories.assistant_memory_repository import AssistantMemoryRepository

        memories = AssistantMemoryRepository(db).list_active(
            user_id=user_id,
            assistant_type=self._validate_assistant_type(assistant_type),
            limit=self.item_limit,
            include_pending=include_pending,
        )
        return self.write_snapshot(user_id=user_id, assistant_type=assistant_type, memories=memories)

    @staticmethod
    def public_metadata(snapshot: dict[str, Any] | None) -> dict[str, Any]:
        if not snapshot:
            return {"available": False, "item_count": 0, "char_count": 0}
        return {
            "available": bool(snapshot.get("available")),
            "assistant_type": snapshot.get("assistant_type"),
            "path": snapshot.get("path"),
            "item_count": int(snapshot.get("item_count") or 0),
            "char_count": int(snapshot.get("char_count") or 0),
            "error": snapshot.get("error"),
        }

    def _safe_memories(self, memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
        active = [memory for memory in memories if memory.get("memory_kind") != "pending"]
        ordered = sorted(
            active[: self.item_limit],
            key=lambda memory: (
                str(memory.get("scope_type") or "global"),
                str(memory.get("memory_kind") or ""),
                str(memory.get("key") or ""),
            ),
        )
        return [
            {
                "scope_type": memory.get("scope_type"),
                "memory_kind": memory.get("memory_kind"),
                "key": memory.get("key"),
                "summary": memory.get("summary"),
                "confidence": memory.get("confidence"),
                "source": memory.get("source"),
            }
            for memory in ordered
        ]

    @staticmethod
    def _snapshot_metadata(*, path: Path, assistant_type: str, item_count: int, content: str) -> dict[str, Any]:
        return {
            "available": True,
            "assistant_type": assistant_type,
            "path": path.as_posix(),
            "item_count": item_count,
            "char_count": len(content),
            "content": content,
        }

    @staticmethod
    def _validate_user_id(user_id: str) -> str:
        try:
            return str(UUID(str(user_id)))
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid user_id for memory snapshot") from exc

    @staticmethod
    def _validate_assistant_type(assistant_type: str) -> str:
        if assistant_type not in ALLOWED_ASSISTANT_TYPES:
            raise ValueError("invalid assistant_type for memory snapshot")
        return assistant_type

    @staticmethod
    def _format_confidence(value: Any) -> str:
        try:
            return f"{float(value):.2f}"
        except (TypeError, ValueError):
            return "0.50"

    @staticmethod
    def _clean_token(value: Any) -> str:
        token = str(value or "unknown").strip()
        token = re.sub(r"[^A-Za-z0-9_.:-]+", "_", token)
        return token.strip("_") or "unknown"

    @staticmethod
    def _clean_summary(value: Any) -> str:
        summary = str(value or "").replace("\r", " ").replace("\n", " ").strip()
        return re.sub(r"\s+", " ", summary)
