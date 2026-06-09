from __future__ import annotations

from dataclasses import dataclass

from app.core.settings import settings
from app.services.dream_memory_service import DreamMemoryService


@dataclass(frozen=True)
class AssistantMemoryCommandResult:
    command: str
    reply: str
    status: str


class AssistantMemoryCommandService:
    def __init__(self, dream_service: DreamMemoryService | None = None):
        self.dream_service = dream_service or DreamMemoryService()

    def handle(self, *, user_id: str, message: str) -> AssistantMemoryCommandResult | None:
        command, args = parse_memory_command(message)
        if command is None:
            return None
        if command == "/dream":
            result = self.dream_service.run(
                user_id=user_id,
                max_batch_size=settings.dream_max_batch_size,
                max_iterations=settings.dream_max_iterations,
                model_override=settings.dream_model_override,
            )
            status = str(result.get("status") or "")
            if status == "nothing_to_process":
                return AssistantMemoryCommandResult(command="dream", reply="Dream: nothing to process.", status=status)
            if status == "completed":
                changed = ", ".join(result.get("changed_files") or []) or "state only"
                sha = str(result.get("commit_sha") or "")[:8]
                return AssistantMemoryCommandResult(
                    command="dream",
                    reply=f"Dream completed.\nCommit: {sha}\nChanged files: {changed}",
                    status=status,
                )
            return AssistantMemoryCommandResult(command="dream", reply=f"Dream: {status}.", status=status)
        if command == "/dream-log":
            reply = self.dream_service.format_log(user_id=user_id, sha=args.strip() or None)
            return AssistantMemoryCommandResult(command="dream-log", reply=reply, status="ok")
        if command == "/dream-restore":
            sha = args.strip()
            if not sha:
                return AssistantMemoryCommandResult(
                    command="dream-restore",
                    reply=self.dream_service.format_restore_points(user_id=user_id),
                    status="list",
                )
            result = self.dream_service.restore(user_id=user_id, sha=sha)
            status = str(result.get("status") or "")
            if status == "restored":
                return AssistantMemoryCommandResult(
                    command="dream-restore",
                    reply=f"Dream restore completed.\nCommit: {str(result.get('commit_sha') or '')[:8]}",
                    status=status,
                )
            return AssistantMemoryCommandResult(
                command="dream-restore",
                reply=f"Dream restore failed: {result.get('error') or 'unknown error'}",
                status=status or "failed",
            )
        return None


def parse_memory_command(message: str | None) -> tuple[str | None, str]:
    stripped = (message or "").strip()
    if not stripped.startswith("/"):
        return None, ""
    parts = stripped.split(maxsplit=1)
    command = parts[0].split("@", 1)[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    if command in {"/dream", "/dream-log", "/dream-restore"}:
        return command, args
    return None, ""
