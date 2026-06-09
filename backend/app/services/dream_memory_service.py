from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.settings import settings
from app.services.ai_assistant_file_memory import AIMemoryFileService


MEMORY_TRACKED_PATHS = [
    "USER.md",
    "SOUL.md",
    "memory/MEMORY.md",
    "memory/history.jsonl",
    ".dream/state.json",
    ".dream/line_state.json",
]

# 阅读入口：Dream 是慢速长期记忆整理器。它先分析 history.jsonl 中的新摘要，
# 再对 USER.md、SOUL.md、memory/MEMORY.md 做最小行级编辑，并把变更提交到
# 用户 runtime 目录内的独立 Git 仓库。


@dataclass(frozen=True)
class DreamMemoryService:
    """执行 Dream 的分析、精确编辑、日志查看和回滚。"""

    root: Path | str | None = None
    file_memory_service: AIMemoryFileService | None = None

    def __post_init__(self) -> None:
        root = self.root or getattr(settings, "ai_assistant_memory_dir", "/app/runtime/ai_assistant_memory")
        object.__setattr__(self, "root", Path(root))

    def run(
        self,
        *,
        user_id: str,
        max_batch_size: int | None = None,
        max_iterations: int | None = None,
        model_override: str | None = None,
        provider: Any | None = None,
    ) -> dict[str, Any]:
        workspace = self._workspace(user_id)
        self._ensure_git_repo(workspace)
        history_items = _read_jsonl(workspace / "memory" / "history.jsonl")
        state = self._read_state(workspace)
        cursor = int(state.get("last_history_cursor") or 0)
        batch_size = max_batch_size or settings.dream_max_batch_size
        batch = history_items[cursor : cursor + batch_size]
        if not batch:
            return {
                "status": "nothing_to_process",
                "changed_files": [],
                "history_items_read": 0,
                "analysis": "",
                "commit_sha": None,
            }

        analysis_plan = self._analyze(workspace=workspace, history_items=batch)
        analysis = self._format_analysis(analysis_plan)
        changed_files = self._apply_edits(workspace=workspace, plan=analysis_plan)
        state["last_history_cursor"] = cursor + len(batch)
        state["last_dream_at"] = _now_iso()
        (workspace / ".dream" / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self._update_line_state(workspace)
        changed_files = sorted(set(changed_files + [".dream/state.json", ".dream/line_state.json"]))
        commit_sha = self._commit_if_changed(workspace, analysis=analysis)
        if commit_sha:
            state["last_commit"] = commit_sha
            (workspace / ".dream" / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self._git(workspace, "add", ".dream/state.json")
            if self._git(workspace, "status", "--porcelain").stdout.strip():
                self._git(workspace, "commit", "--amend", "--no-edit")
                commit_sha = self._git(workspace, "rev-parse", "HEAD").stdout.strip()
        return {
            "status": "completed" if commit_sha else "no_changes",
            "changed_files": self._changed_files_for_commit(workspace, commit_sha) if commit_sha else changed_files,
            "history_items_read": len(batch),
            "analysis": analysis,
            "commit_sha": commit_sha,
            "model_override": model_override,
            "max_iterations": max_iterations,
            "provider_used": getattr(provider, "name", None),
        }

    def build_phase1_prompt(self, *, user_id: str, history_items: list[dict[str, Any]]) -> str:
        workspace = self._workspace(user_id)
        user_md = (workspace / "USER.md").read_text(encoding="utf-8")
        soul_md = (workspace / "SOUL.md").read_text(encoding="utf-8")
        memory_md = self._memory_md_with_age(workspace)
        history = "\n".join(json.dumps(item, ensure_ascii=False, default=str) for item in history_items)
        return (
            "Phase 1 Dream analysis prompt\n"
            "Analyze new history, corrections, stale entries, duplicates, and proposed line edits.\n\n"
            f"USER.md:\n{user_md}\n\nSOUL.md:\n{soul_md}\n\nmemory/MEMORY.md:\n{memory_md}\n\nhistory.jsonl batch:\n{history}\n"
        )

    def format_log(self, *, user_id: str, sha: str | None = None) -> str:
        workspace = self._workspace(user_id)
        self._ensure_git_repo(workspace)
        target = sha or self._latest_dream_commit(workspace)
        if not target:
            return "Dream log: no Dream commits yet."
        show = self._git(
            workspace,
            "show",
            "--stat",
            "--patch",
            "--format=Commit: %H%nTime: %cI%nSubject: %s%nBody:%n%b",
            target,
            "--",
            *MEMORY_TRACKED_PATHS,
            check=False,
        )
        if show.returncode != 0:
            return f"Dream log not found: {target}"
        changed = self._git(
            workspace,
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            target,
            check=False,
        ).stdout.strip()
        return f"## Dream Update\nChanged files: {changed or '(none)'}\n\n{show.stdout.strip()}"

    def list_restore_points(self, *, user_id: str, limit: int = 10) -> list[dict[str, str]]:
        workspace = self._workspace(user_id)
        self._ensure_git_repo(workspace)
        result = self._git(
            workspace,
            "log",
            f"--max-count={limit}",
            "--format=%H%x09%cI%x09%s",
            check=False,
        )
        points: list[dict[str, str]] = []
        for line in result.stdout.splitlines():
            parts = line.split("\t", 2)
            if len(parts) != 3:
                continue
            sha, committed_at, subject = parts
            if subject.startswith("Dream update") or subject.startswith("Dream restore"):
                points.append({"sha": sha, "time": committed_at, "subject": subject})
        return points

    def format_restore_points(self, *, user_id: str, limit: int = 10) -> str:
        points = self.list_restore_points(user_id=user_id, limit=limit)
        if not points:
            return "Dream restore: no Dream commits yet."
        lines = ["Dream restore points:"]
        for point in points:
            lines.append(f"- {point['sha'][:8]} {point['time']} {point['subject']}")
        return "\n".join(lines)

    def restore(self, *, user_id: str, sha: str) -> dict[str, Any]:
        workspace = self._workspace(user_id)
        self._ensure_git_repo(workspace)
        result = self._git(workspace, "revert", "--no-commit", sha, check=False)
        if result.returncode != 0:
            self._git(workspace, "revert", "--abort", check=False)
            return {"status": "failed", "error": result.stderr.strip() or result.stdout.strip(), "commit_sha": None}
        self._git(
            workspace,
            "commit",
            "-m",
            f"Dream restore {sha[:8]}",
            "-m",
            f"Restored memory files to the state before {sha}.",
        )
        commit_sha = self._git(workspace, "rev-parse", "HEAD").stdout.strip()
        return {"status": "restored", "commit_sha": commit_sha}

    def run_due_users(self, *, provider: Any | None = None, max_users: int | None = None) -> int:
        users_root = Path(self.root) / "users"
        if not settings.dream_enabled or not users_root.exists():
            return 0
        processed = 0
        for workspace in sorted(path for path in users_root.iterdir() if path.is_dir()):
            state = self._read_state(workspace)
            history_count = len(_read_jsonl(workspace / "memory" / "history.jsonl"))
            if history_count <= int(state.get("last_history_cursor") or 0):
                continue
            result = self.run(
                user_id=workspace.name,
                max_batch_size=settings.dream_max_batch_size,
                max_iterations=settings.dream_max_iterations,
                model_override=settings.dream_model_override,
                provider=provider,
            )
            if result.get("status") in {"completed", "no_changes"}:
                processed += 1
            if max_users is not None and processed >= max_users:
                break
        return processed

    def _workspace(self, user_id: str) -> Path:
        service = self.file_memory_service or AIMemoryFileService(root=self.root)
        return service.workspace_for_user(user_id)

    def _analyze(self, *, workspace: Path, history_items: list[dict[str, Any]]) -> dict[str, Any]:
        user_md = (workspace / "USER.md").read_text(encoding="utf-8")
        soul_md = (workspace / "SOUL.md").read_text(encoding="utf-8")
        memory_md = (workspace / "memory" / "MEMORY.md").read_text(encoding="utf-8")
        extracted = self._extract_history_facts(history_items)
        user_add = _missing_lines(user_md, extracted["user_facts"])
        memory_add = _missing_lines(memory_md, extracted["decisions"] + extracted["solutions"] + extracted["events"])
        soul_add = _missing_lines(soul_md, extracted["soul"])
        removals = self._duplicate_memory_removals(user_md=user_md, soul_md=soul_md, memory_md=memory_md)
        return {
            "new_facts": extracted,
            "corrections": [],
            "stale_entries": [],
            "duplicates": removals,
            "edits": {
                "USER.md": {"add": user_add, "remove": []},
                "SOUL.md": {"add": soul_add, "remove": []},
                "memory/MEMORY.md": {"add": memory_add, "remove": removals},
            },
        }

    def _format_analysis(self, plan: dict[str, Any]) -> str:
        lines = ["Phase 1 Analysis"]
        facts = plan.get("new_facts") or {}
        for label, key in [
            ("New user facts", "user_facts"),
            ("Decisions", "decisions"),
            ("Solutions", "solutions"),
            ("Events", "events"),
            ("Soul/style", "soul"),
        ]:
            values = facts.get(key) or []
            lines.append(f"{label}:")
            lines.extend(f"- {_sanitize_text(value)}" for value in values) if values else lines.append("- none")
        lines.append("Corrections:")
        lines.append("- none")
        lines.append("Stale entries:")
        lines.append("- none")
        lines.append("Duplicates and removals:")
        removals = plan.get("duplicates") or []
        if removals:
            lines.extend(f"- [FILE-REMOVE] memory/MEMORY.md: {_sanitize_text(line)}" for line in removals)
        else:
            lines.append("- none")
        lines.append("Suggested edits:")
        for file_name, edits in (plan.get("edits") or {}).items():
            for line in edits.get("add") or []:
                lines.append(f"- [FILE-ADD] {file_name}: {_sanitize_text(line)}")
            for line in edits.get("remove") or []:
                lines.append(f"- [FILE-REMOVE] {file_name}: {_sanitize_text(line)}")
        return "\n".join(lines)

    def _apply_edits(self, *, workspace: Path, plan: dict[str, Any]) -> list[str]:
        changed: list[str] = []
        for file_name, edits in (plan.get("edits") or {}).items():
            path = workspace / file_name
            before = path.read_text(encoding="utf-8")
            after = _remove_lines(before, edits.get("remove") or [])
            after = _append_lines(after, edits.get("add") or [])
            if after != before:
                path.write_text(after, encoding="utf-8")
                changed.append(file_name)
        return changed

    def _extract_history_facts(self, history_items: list[dict[str, Any]]) -> dict[str, list[str]]:
        extracted: dict[str, list[str]] = {"user_facts": [], "decisions": [], "solutions": [], "events": [], "soul": []}
        for item in history_items:
            facts = item.get("facts") if isinstance(item.get("facts"), dict) else {}
            for key in ["user_facts", "decisions", "solutions", "events"]:
                values = facts.get(key) if isinstance(facts, dict) else None
                if isinstance(values, list):
                    extracted[key].extend(str(value) for value in values)
            summary = str(item.get("summary") or "")
            extracted["user_facts"].extend(_extract_summary_segments(summary, "User fact"))
            extracted["decisions"].extend(_extract_summary_segments(summary, "Decision"))
            extracted["solutions"].extend(_extract_summary_segments(summary, "Solution"))
            extracted["events"].extend(_extract_summary_segments(summary, "Event"))
            if re.search(r"\b(concise|direct|tone|style)\b", summary, re.IGNORECASE):
                extracted["soul"].extend(_extract_summary_segments(summary, "Style"))
        return {key: _unique([_markdown_line(value) for value in values]) for key, values in extracted.items()}

    @staticmethod
    def _duplicate_memory_removals(*, user_md: str, soul_md: str, memory_md: str) -> list[str]:
        permanent = {_normalized_line(line) for line in user_md.splitlines() + soul_md.splitlines() if line.strip().startswith("-")}
        removals: list[str] = []
        for line in memory_md.splitlines():
            if not line.strip().startswith("-"):
                continue
            if _normalized_line(line) in permanent:
                removals.append(line.strip())
        return removals

    def _memory_md_with_age(self, workspace: Path) -> str:
        memory_path = workspace / "memory" / "MEMORY.md"
        line_state = self._read_line_state(workspace)
        memory_state = line_state.get("memory/MEMORY.md", {}) if isinstance(line_state, dict) else {}
        today = datetime.now(timezone.utc)
        lines: list[str] = []
        for line in memory_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            seen_at = memory_state.get(stripped)
            if stripped.startswith("-") and seen_at:
                try:
                    age_days = max(0, (today - datetime.fromisoformat(str(seen_at))).days)
                except ValueError:
                    age_days = 0
                if age_days > 14:
                    lines.append(f"{line}  \u2190 {age_days}d")
                    continue
            lines.append(line)
        return "\n".join(lines)

    def _update_line_state(self, workspace: Path) -> None:
        line_state = self._read_line_state(workspace)
        memory_state = dict((line_state.get("memory/MEMORY.md") or {}) if isinstance(line_state, dict) else {})
        now = _now_iso()
        current_lines = {
            line.strip()
            for line in (workspace / "memory" / "MEMORY.md").read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("-")
        }
        updated = {line: memory_state.get(line, now) for line in current_lines}
        (workspace / ".dream" / "line_state.json").write_text(
            json.dumps({"memory/MEMORY.md": updated}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _read_state(self, workspace: Path) -> dict[str, Any]:
        path = workspace / ".dream" / "state.json"
        if not path.exists():
            return {"last_history_cursor": 0, "last_dream_at": None, "last_commit": None}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"last_history_cursor": 0, "last_dream_at": None, "last_commit": None}
        return value if isinstance(value, dict) else {"last_history_cursor": 0, "last_dream_at": None, "last_commit": None}

    def _read_line_state(self, workspace: Path) -> dict[str, Any]:
        path = workspace / ".dream" / "line_state.json"
        if not path.exists():
            return {"memory/MEMORY.md": {}}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"memory/MEMORY.md": {}}
        return value if isinstance(value, dict) else {"memory/MEMORY.md": {}}

    def _ensure_git_repo(self, workspace: Path) -> None:
        if not (workspace / ".git").exists():
            self._git(workspace, "init")
        self._git(workspace, "config", "user.name", "Dream Memory")
        self._git(workspace, "config", "user.email", "dream-memory@example.local")
        if not (workspace / ".gitignore").exists():
            (workspace / ".gitignore").write_text("sessions/\n", encoding="utf-8")
        if not self._has_commits(workspace):
            self._git(workspace, "add", *MEMORY_TRACKED_PATHS, ".gitignore")
            self._git(workspace, "commit", "-m", "Initialize dream memory workspace", check=False)

    def _has_commits(self, workspace: Path) -> bool:
        return self._git(workspace, "rev-parse", "--verify", "HEAD", check=False).returncode == 0

    def _commit_if_changed(self, workspace: Path, *, analysis: str) -> str | None:
        self._git(workspace, "add", *MEMORY_TRACKED_PATHS, ".gitignore")
        status = self._git(workspace, "status", "--porcelain").stdout.strip()
        if not status:
            return None
        message = "Dream update memory"
        self._git(workspace, "commit", "-m", message, "-m", analysis)
        return self._git(workspace, "rev-parse", "HEAD").stdout.strip()

    def _changed_files_for_commit(self, workspace: Path, sha: str | None) -> list[str]:
        if not sha:
            return []
        result = self._git(workspace, "diff-tree", "--no-commit-id", "--name-only", "-r", sha, check=False)
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def _latest_dream_commit(self, workspace: Path) -> str | None:
        result = self._git(
            workspace,
            "log",
            "--format=%H%x09%s",
            check=False,
        )
        for line in result.stdout.splitlines():
            parts = line.split("\t", 1)
            if len(parts) == 2 and (parts[1].startswith("Dream update") or parts[1].startswith("Dream restore")):
                return parts[0]
        return None

    @staticmethod
    def _git(workspace: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", *args],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        if check and result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"git {' '.join(args)} failed")
        return result


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


def _extract_summary_segments(summary: str, label: str) -> list[str]:
    pattern = re.compile(rf"{re.escape(label)}\s*:\s*([^.;]+)", re.IGNORECASE)
    return [match.group(1).strip() for match in pattern.finditer(summary)]


def _missing_lines(markdown: str, candidates: list[str]) -> list[str]:
    existing = {_normalized_line(line) for line in markdown.splitlines() if line.strip().startswith("-")}
    return [line for line in candidates if _normalized_line(line) not in existing]


def _append_lines(markdown: str, lines: list[str]) -> str:
    to_add = _missing_lines(markdown, lines)
    if not to_add:
        return markdown
    return markdown.rstrip() + "\n" + "\n".join(to_add) + "\n"


def _remove_lines(markdown: str, removals: list[str]) -> str:
    if not removals:
        return markdown
    removal_keys = {_normalized_line(line) for line in removals}
    kept = [line for line in markdown.splitlines() if _normalized_line(line) not in removal_keys]
    return "\n".join(kept).rstrip() + "\n"


def _markdown_line(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(value)).strip(" .;|-")
    if not cleaned:
        return ""
    return "- " + cleaned[:220]


def _normalized_line(value: str) -> str:
    text = str(value).strip()
    text = re.sub(r"^-\s*", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.casefold()


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value:
            continue
        key = _normalized_line(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _sanitize_text(value: str) -> str:
    text = re.sub(r"(api[_-]?key|token|secret|password)\s*[:=]\s*\S+", r"\1=[REDACTED]", str(value), flags=re.IGNORECASE)
    return text[:500]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
