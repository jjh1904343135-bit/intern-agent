from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.settings import settings


DEFAULT_USER_MD = "# USER\n\n- 尚未形成稳定用户画像。\n"
DEFAULT_MEMORY_MD = "# MEMORY\n\n- 青程 AI 会根据已确认的会话摘要沉淀求职偏好和项目事实。\n"
DEFAULT_SOUL_MD = "# SOUL\n\n- 回答保持简洁、诚实、行动导向。\n"


@dataclass(frozen=True)
class AIMemoryFileService:
    """AI 助手的文件化长期上下文；业务权威数据仍在 PostgreSQL。"""

    root: Path | str | None = None
    consolidation_char_limit: int = 6000
    keep_recent_messages: int = 6

    def __post_init__(self) -> None:
        root = self.root or getattr(settings, "ai_assistant_memory_dir", "/app/runtime/ai_assistant_memory")
        object.__setattr__(self, "root", Path(root))

    def append_session_message(
        self,
        *,
        user_id: str,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        workspace = self._ensure_workspace(user_id)
        session_path = workspace / "sessions" / f"{session_id}.jsonl"
        # 每轮对话按 JSONL 追加，方便后续压缩，同时保留原始会话归档。
        item = {
            "ts": _now_iso(),
            "session_id": session_id,
            "role": role,
            "content": content,
            "metadata": _safe_metadata(metadata or {}),
        }
        with session_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")
        return {"path": str(session_path), "role": role, "char_count": len(content)}

    def read_context(self, *, user_id: str, session_id: str, max_history_items: int = 8) -> dict[str, Any]:
        workspace = self._ensure_workspace(user_id)
        # 模型读取的是近期会话、压缩历史和三份 Markdown 画像，不直接读取完整数据库。
        session_items = self._read_jsonl(workspace / "sessions" / f"{session_id}.jsonl")
        history_items = self._read_jsonl(workspace / "memory" / "history.jsonl")[-max_history_items:]
        user_md = (workspace / "USER.md").read_text(encoding="utf-8")
        memory_md = (workspace / "MEMORY.md").read_text(encoding="utf-8")
        soul_md = (workspace / "SOUL.md").read_text(encoding="utf-8")
        files_used = [
            {"name": "USER.md", "path": str(workspace / "USER.md")},
            {"name": "MEMORY.md", "path": str(workspace / "MEMORY.md")},
            {"name": "SOUL.md", "path": str(workspace / "SOUL.md")},
            {"name": "history.jsonl", "path": str(workspace / "memory" / "history.jsonl")},
            {"name": "session", "path": str(workspace / "sessions" / f"{session_id}.jsonl")},
        ]
        return {
            "assistant_type": "ai_assistant",
            "workspace": str(workspace),
            "session_recent": session_items[-self.keep_recent_messages :],
            "history_items": history_items,
            "USER.md": user_md,
            "MEMORY.md": memory_md,
            "SOUL.md": soul_md,
            "files_used": files_used,
            "summary_text": self._context_summary(user_md=user_md, memory_md=memory_md, soul_md=soul_md, history_items=history_items),
        }

    def soft_consolidate(self, *, user_id: str, session_id: str) -> dict[str, Any]:
        workspace = self._ensure_workspace(user_id)
        session_path = workspace / "sessions" / f"{session_id}.jsonl"
        items = self._read_jsonl(session_path)
        total_chars = sum(len(str(item.get("content") or "")) for item in items)
        if total_chars <= self.consolidation_char_limit or len(items) <= self.keep_recent_messages:
            return {"compacted": False, "reason": "below_threshold", "total_chars": total_chars}

        # soft consolidation 只追加摘要，不删除 session JSONL，便于审计和恢复。
        cursor = max(0, len(items) - self.keep_recent_messages)
        history_path = workspace / "memory" / "history.jsonl"
        existing = self._read_jsonl(history_path)
        if any(item.get("session_id") == session_id and int(item.get("cursor") or 0) >= cursor for item in existing):
            return {"compacted": False, "reason": "already_compacted", "cursor": cursor, "total_chars": total_chars}

        summary_source = items[:cursor]
        summary = self._summarize_messages(summary_source)
        history_item = {
            "ts": _now_iso(),
            "session_id": session_id,
            "cursor": cursor,
            "message_count": len(summary_source),
            "summary": summary,
            "source_ref": {"kind": "chat_session", "session_id": session_id, "cursor": cursor},
        }
        with history_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(history_item, ensure_ascii=False) + "\n")
        return {
            "compacted": True,
            "cursor": cursor,
            "message_count": len(summary_source),
            "history_path": str(history_path),
            "summary": summary,
            "total_chars": total_chars,
        }

    def dream_update(self, *, user_id: str) -> dict[str, Any]:
        workspace = self._ensure_workspace(user_id)
        history_items = self._read_jsonl(workspace / "memory" / "history.jsonl")
        if not history_items:
            return {"updated_files": [], "history_items_read": 0}

        # Dream 第一版是本地规则沉淀稳定偏好，不调用模型、不写 git、不暴露推理链。
        text = "\n".join(str(item.get("summary") or "") for item in history_items[-20:])
        updates: dict[str, list[str]] = {"USER.md": [], "MEMORY.md": [], "SOUL.md": []}
        for city in ["北京", "上海", "深圳", "杭州", "广州", "成都"]:
            if city in text:
                updates["USER.md"].append(f"- 目标城市偏好：{city}")
        for role in ["Java 后端", "后端", "产品", "数据分析", "算法", "测试"]:
            if role in text:
                updates["USER.md"].append(f"- 关注岗位方向：{role}")
        for company in ["腾讯", "阿里", "字节", "美团", "百度"]:
            if company in text:
                updates["USER.md"].append(f"- 关注公司：{company}")
        if "投递" in text:
            updates["MEMORY.md"].append("- 用户希望求职建议能落到投递动作和后续跟进。")
        if "简历" in text:
            updates["MEMORY.md"].append("- 回答简历相关问题时应优先引用默认简历事实。")
        updates["SOUL.md"].append("- 保持简洁，不把工具上下文和内部推理链暴露给用户。")

        updated_files: list[str] = []
        for file_name, lines in updates.items():
            unique_lines = list(dict.fromkeys(line for line in lines if line.strip()))
            if not unique_lines:
                continue
            path = workspace / file_name
            current = path.read_text(encoding="utf-8")
            appended = [line for line in unique_lines if line not in current]
            if appended:
                path.write_text(current.rstrip() + "\n" + "\n".join(appended) + "\n", encoding="utf-8")
                updated_files.append(file_name)
        return {"updated_files": updated_files, "history_items_read": len(history_items)}

    def public_context_metadata(self, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "assistant_type": "ai_assistant",
            "count": len(context.get("history_items") or []),
            "items": [
                {"summary": item.get("summary"), "source_ref": item.get("source_ref") or {}}
                for item in list(context.get("history_items") or [])[-5:]
            ],
            "memory_files": [item["name"] for item in context.get("files_used") or []],
            "memory_snapshot": {
                "available": True,
                "assistant_type": "ai_assistant",
                "path": str(Path(context["workspace"]) / "MEMORY.md") if context.get("workspace") else None,
                "item_count": len(context.get("history_items") or []),
                "char_count": len(str(context.get("summary_text") or "")),
            },
        }

    def _ensure_workspace(self, user_id: str) -> Path:
        workspace = Path(self.root) / "users" / str(user_id)
        (workspace / "sessions").mkdir(parents=True, exist_ok=True)
        (workspace / "memory").mkdir(parents=True, exist_ok=True)
        self._ensure_file(workspace / "USER.md", DEFAULT_USER_MD)
        self._ensure_file(workspace / "MEMORY.md", DEFAULT_MEMORY_MD)
        self._ensure_file(workspace / "SOUL.md", DEFAULT_SOUL_MD)
        self._ensure_file(workspace / "memory" / "history.jsonl", "")
        return workspace

    @staticmethod
    def _ensure_file(path: Path, default: str) -> None:
        if not path.exists():
            path.write_text(default, encoding="utf-8")

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        items: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                items.append(payload)
        return items

    @staticmethod
    def _summarize_messages(items: list[dict[str, Any]]) -> str:
        snippets = []
        for item in items[-8:]:
            role = str(item.get("role") or "message")
            content = str(item.get("content") or "").replace("\n", " ").strip()
            if content:
                snippets.append(f"{role}: {content[:120]}")
        return "；".join(snippets)[:1200]

    @staticmethod
    def _context_summary(*, user_md: str, memory_md: str, soul_md: str, history_items: list[dict[str, Any]]) -> str:
        history = "；".join(str(item.get("summary") or "")[:180] for item in history_items[-5:])
        return f"USER:\n{user_md[:1200]}\nMEMORY:\n{memory_md[:1200]}\nSOUL:\n{soul_md[:800]}\nHISTORY:\n{history}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    blocked = {"raw_prompt", "prompt", "messages", "api_key", "token"}
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        if key in blocked:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
        elif isinstance(value, (list, dict)):
            safe[key] = json.loads(json.dumps(value, ensure_ascii=False, default=str))
        else:
            safe[key] = str(value)
    return safe
