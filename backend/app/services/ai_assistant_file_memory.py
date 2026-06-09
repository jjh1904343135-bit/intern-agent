from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.settings import settings


DEFAULT_USER_MD = "# USER\n\n- No stable user profile facts have been confirmed yet.\n"
DEFAULT_MEMORY_MD = "# MEMORY\n\n- Project knowledge will be added here after confirmed conversation summaries.\n"
DEFAULT_SOUL_MD = "# SOUL\n\n- Be concise, honest, and action-oriented.\n"
DEFAULT_DREAM_STATE = {
    "last_history_cursor": 0,
    "last_dream_at": None,
    "last_commit": None,
}


@dataclass(frozen=True)
class AIMemoryFileService:
    """File-backed runtime memory for the AI assistant.

    PostgreSQL remains the source of truth for chat sessions and business data.
    This service only owns the assistant runtime memory workspace.
    """

    root: Path | str | None = None
    consolidation_char_limit: int = 6000
    keep_recent_messages: int = 6

    def __post_init__(self) -> None:
        root = self.root or getattr(settings, "ai_assistant_memory_dir", "/app/runtime/ai_assistant_memory")
        object.__setattr__(self, "root", Path(root))

    def workspace_for_user(self, user_id: str) -> Path:
        return self._ensure_workspace(user_id)

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
        session_path = workspace / "sessions" / f"{session_id}.jsonl"
        history_path = workspace / "memory" / "history.jsonl"
        memory_path = workspace / "memory" / "MEMORY.md"
        session_items = self._read_jsonl(session_path)
        history_items = self._read_jsonl(history_path)[-max_history_items:]
        user_md = (workspace / "USER.md").read_text(encoding="utf-8")
        memory_md = memory_path.read_text(encoding="utf-8")
        soul_md = (workspace / "SOUL.md").read_text(encoding="utf-8")
        files_used = [
            {"name": "USER.md", "path": str(workspace / "USER.md")},
            {"name": "SOUL.md", "path": str(workspace / "SOUL.md")},
            {"name": "memory/MEMORY.md", "path": str(memory_path)},
            {"name": "memory/history.jsonl", "path": str(history_path)},
            {"name": "session", "path": str(session_path)},
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
            "summary_text": self._context_summary(
                user_md=user_md,
                memory_md=memory_md,
                soul_md=soul_md,
                history_items=history_items,
            ),
        }

    def soft_consolidate(self, *, user_id: str, session_id: str, force: bool = False) -> dict[str, Any]:
        workspace = self._ensure_workspace(user_id)
        session_path = workspace / "sessions" / f"{session_id}.jsonl"
        items = self._read_jsonl(session_path)
        total_chars = sum(len(str(item.get("content") or "")) for item in items)
        if len(items) <= self.keep_recent_messages:
            return {"compacted": False, "reason": "too_few_messages", "total_chars": total_chars}
        if not force and total_chars <= self.consolidation_char_limit:
            return {"compacted": False, "reason": "below_threshold", "total_chars": total_chars}

        cursor = max(0, len(items) - self.keep_recent_messages)
        history_path = workspace / "memory" / "history.jsonl"
        existing = self._read_jsonl(history_path)
        if any(item.get("session_id") == session_id and int(item.get("cursor") or 0) >= cursor for item in existing):
            return {"compacted": False, "reason": "already_compacted", "cursor": cursor, "total_chars": total_chars}

        summary_source = items[:cursor]
        facts = self._extract_facts(summary_source)
        summary = self._summarize_messages(summary_source, facts=facts)
        history_item = {
            "ts": _now_iso(),
            "session_id": session_id,
            "cursor": cursor,
            "message_count": len(summary_source),
            "summary": summary,
            "facts": facts,
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
            "facts": facts,
            "total_chars": total_chars,
            "reason": "forced" if force else "above_threshold",
        }

    def public_context_metadata(self, context: dict[str, Any]) -> dict[str, Any]:
        workspace = Path(context["workspace"]) if context.get("workspace") else None
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
                "path": str(workspace / "memory" / "MEMORY.md") if workspace else None,
                "item_count": len(context.get("history_items") or []),
                "char_count": len(str(context.get("summary_text") or "")),
            },
        }

    def _ensure_workspace(self, user_id: str) -> Path:
        workspace = Path(self.root) / "users" / str(user_id)
        (workspace / "sessions").mkdir(parents=True, exist_ok=True)
        (workspace / "memory").mkdir(parents=True, exist_ok=True)
        (workspace / ".dream").mkdir(parents=True, exist_ok=True)
        self._ensure_file(workspace / "USER.md", DEFAULT_USER_MD)
        self._ensure_memory_file(workspace)
        self._ensure_file(workspace / "SOUL.md", DEFAULT_SOUL_MD)
        self._ensure_file(workspace / "memory" / "history.jsonl", "")
        self._ensure_json_file(workspace / ".dream" / "state.json", DEFAULT_DREAM_STATE)
        self._ensure_json_file(workspace / ".dream" / "line_state.json", {"memory/MEMORY.md": {}})
        return workspace

    def _ensure_memory_file(self, workspace: Path) -> None:
        old_path = workspace / "MEMORY.md"
        new_path = workspace / "memory" / "MEMORY.md"
        if old_path.exists():
            old_text = old_path.read_text(encoding="utf-8")
            if new_path.exists():
                current = new_path.read_text(encoding="utf-8")
                merged = _merge_markdown_lines(current, old_text)
                if merged != current:
                    new_path.write_text(merged, encoding="utf-8")
            else:
                new_path.write_text(old_text, encoding="utf-8")
            old_path.unlink()
        self._ensure_file(new_path, DEFAULT_MEMORY_MD)

    @staticmethod
    def _ensure_file(path: Path, default: str) -> None:
        if not path.exists():
            path.write_text(default, encoding="utf-8")

    @staticmethod
    def _ensure_json_file(path: Path, default: dict[str, Any]) -> None:
        if path.exists():
            return
        path.write_text(json.dumps(default, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

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
    def _summarize_messages(items: list[dict[str, Any]], *, facts: dict[str, list[str]]) -> str:
        sections: list[str] = []
        labels = {
            "user_facts": "User facts",
            "decisions": "Decisions",
            "solutions": "Solutions",
            "events": "Events",
        }
        for key, label in labels.items():
            values = facts.get(key) or []
            if values:
                sections.append(f"{label}: " + "; ".join(values[:8]))
        snippets = []
        for item in items[-8:]:
            role = str(item.get("role") or "message")
            content = str(item.get("content") or "").replace("\n", " ").strip()
            if content and not _looks_source_derived(content):
                snippets.append(f"{role}: {content[:160]}")
        if snippets:
            sections.append("Recent source: " + " | ".join(snippets))
        return " ".join(sections)[:1800]

    @staticmethod
    def _extract_facts(items: list[dict[str, Any]]) -> dict[str, list[str]]:
        facts: dict[str, list[str]] = {"user_facts": [], "decisions": [], "solutions": [], "events": []}
        for item in items:
            content = str(item.get("content") or "").replace("\n", " ").strip()
            if not content or _looks_source_derived(content):
                continue
            for category, prefix in [
                ("user_facts", "user fact"),
                ("decisions", "decision"),
                ("solutions", "solution"),
                ("events", "event"),
            ]:
                facts[category].extend(_extract_prefixed_segments(content, prefix))
            lowered = content.lower()
            if any(word in lowered for word in ["prefer", "prefers", "preference", "lives in", "targeting"]):
                facts["user_facts"].append(_clean_fact(content))
            if any(word in lowered for word in ["decided", "choose ", "chosen ", "use postgresql", "use redis"]):
                facts["decisions"].append(_clean_fact(content))
            if any(word in lowered for word in ["fixed", "workaround", "retry", "solved"]):
                facts["solutions"].append(_clean_fact(content))
            if any(word in lowered for word in ["deadline", "interview", "event:", "due "]):
                facts["events"].append(_clean_fact(content))
        return {key: _unique(values) for key, values in facts.items()}

    @staticmethod
    def _context_summary(*, user_md: str, memory_md: str, soul_md: str, history_items: list[dict[str, Any]]) -> str:
        history = " | ".join(str(item.get("summary") or "")[:240] for item in history_items[-5:])
        return f"USER:\n{user_md[:1200]}\nMEMORY:\n{memory_md[:1200]}\nSOUL:\n{soul_md[:800]}\nHISTORY:\n{history}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    blocked = {"raw_prompt", "prompt", "messages", "api_key", "token", "secret"}
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        if key.lower() in blocked:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
        elif isinstance(value, (list, dict)):
            safe[key] = json.loads(json.dumps(value, ensure_ascii=False, default=str))
        else:
            safe[key] = str(value)
    return safe


def _extract_prefixed_segments(content: str, prefix: str) -> list[str]:
    pattern = re.compile(rf"{re.escape(prefix)}\s*:\s*([^.;|]+)", re.IGNORECASE)
    return [_clean_fact(match.group(1)) for match in pattern.finditer(content)]


def _clean_fact(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip(" .;|-")
    return cleaned[:220]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = _clean_fact(value)
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


def _looks_source_derived(content: str) -> bool:
    lowered = content.lower()
    if any(marker in lowered for marker in ["git commit", "git status", "```", "traceback", "pytest"]):
        return True
    return bool(re.search(r"(^|\n)\s*(def|class|import)\s+[a-zA-Z_][\w_]*", content))


def _merge_markdown_lines(current: str, incoming: str) -> str:
    lines = current.rstrip().splitlines()
    existing = {line.strip() for line in lines if line.strip()}
    for line in incoming.splitlines():
        stripped = line.strip()
        if not stripped or stripped in existing:
            continue
        lines.append(line)
        existing.add(stripped)
    return "\n".join(lines).rstrip() + "\n"
