from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.settings import settings
from app.repositories.scheduled_task_repository import ScheduledTaskRepository
from app.services.scheduled_task_parser import ScheduledTaskIntentDetector


@dataclass
class ScheduledTaskChatResult:
    handled: bool
    action: str | None = None
    reply: str = ""
    task: Any | None = None
    inbox_item: Any | None = None
    metadata: dict[str, Any] | None = None


class ScheduledTaskService:
    # 定时任务只能调用项目内安全工具，不能执行 shell，也不能自动提交外部投递。
    ALLOWED_TASK_TOOLS = (
        "chat_answer",
        "resume_profile",
        "job_search",
        "application_list",
        "knowledge_search",
        "telegram_send",
    )

    def __init__(self, *, repository: ScheduledTaskRepository | Any):
        self.repository = repository
        self.detector = ScheduledTaskIntentDetector()

    def handle_chat_message(
        self,
        *,
        user_id: str,
        message: str,
        session_id: str | None,
        channel: str,
        telegram_chat_id: str | None = None,
        now: datetime | None = None,
    ) -> ScheduledTaskChatResult:
        current = now or datetime.utcnow()
        parser_now = current if now is not None else self._utc_to_local(current, settings.telegram_timezone)
        intent = self.detector.detect(message, now=parser_now, timezone_name=settings.telegram_timezone)
        if not intent.handled:
            return ScheduledTaskChatResult(handled=False)
        if intent.action == "clarify":
            return ScheduledTaskChatResult(
                handled=True,
                action="clarify",
                reply=intent.reply,
                metadata={"scheduled_task_action": "clarify", "confidence": intent.confidence},
            )
        if intent.action == "list":
            tasks = self.repository.list_tasks(user_id=user_id, limit=10)
            return ScheduledTaskChatResult(
                handled=True,
                action="list",
                reply=self._format_task_list(tasks),
                metadata={"scheduled_task_action": "list", "task_count": len(tasks)},
            )
        if intent.action in {"cancel", "pause", "resume"}:
            task = self.repository.find_task(user_id=user_id, selector=intent.selector or "")
            if task is None:
                return ScheduledTaskChatResult(
                    handled=True,
                    action=intent.action,
                    reply="没有找到这个任务。你可以先说“列出我的定时任务”查看任务 ID。",
                    metadata={"scheduled_task_action": intent.action, "selector": intent.selector, "status": "not_found"},
                )
            target_status = {"cancel": "cancelled", "pause": "paused", "resume": "enabled"}[intent.action]
            updated = self.repository.update_status(task=task, status=target_status)
            return ScheduledTaskChatResult(
                handled=True,
                action=intent.action,
                task=updated,
                reply=f"已{self._action_label(intent.action)}任务：{self._get(updated, 'title')}。",
                metadata=self._task_metadata(updated, scheduled_task_action=intent.action),
            )
        if intent.action == "create":
            # 创建时记录来源通道；Telegram 来源的任务执行结果会回到同一个 chat。
            task = self.repository.create_task(
                user_id=user_id,
                source_session_id=session_id,
                assistant_type="ai_assistant",
                title=intent.title or "定时任务",
                instruction=intent.instruction or message,
                schedule_type=intent.schedule_type,
                schedule_value=intent.schedule_value,
                timezone=intent.timezone,
                next_run_at=intent.next_run_at_utc,
                status="enabled",
                source_channel=channel,
                delivery_channel="telegram" if channel == "telegram" else "inbox",
                telegram_chat_id=telegram_chat_id,
                deliver=True,
                tool_allowlist=list(self.ALLOWED_TASK_TOOLS),
                task_metadata={
                    "created_from": channel,
                    "parse_confidence": intent.confidence,
                    "local_next_run_at": intent.next_run_at_local,
                    "safety": "service_allowlist_only_no_shell_no_auto_apply",
                },
            )
            delivery_note = (
                "结果会直接发到当前 Telegram 聊天，并同步进入任务收件箱。"
                if channel == "telegram"
                else "结果会进入任务收件箱。"
            )
            return ScheduledTaskChatResult(
                handled=True,
                action="create",
                task=task,
                reply=f"已创建定时任务：{self._get(task, 'title')}。下次执行：{self._format_local_time(self._get(task, 'next_run_at'), self._get(task, 'timezone'))}。{delivery_note}",
                metadata=self._task_metadata(task, scheduled_task_action="create"),
            )
        return ScheduledTaskChatResult(handled=False)

    async def execute_due_tasks(self, *, now: datetime | None = None, bot_client: Any | None = None, limit: int = 5) -> int:
        current = now or datetime.utcnow()
        # claim_due_tasks 负责抢占到期任务，避免多个 worker 重复执行同一任务。
        tasks = self.repository.claim_due_tasks(now=current, limit=limit)
        executed = 0
        for task in tasks:
            run = self.repository.create_run(task=task, now=current)
            try:
                output, metadata = await self._execute_task_with_chat(task=task)
                inbox_item = None
                if bool(self._get(task, "deliver")):
                    inbox_item = self.repository.record_inbox(
                        user_id=str(self._get(task, "user_id")),
                        task_id=str(self._get(task, "id")),
                        task_run_id=str(self._get(run, "id")),
                        title=self._get(task, "title"),
                        content=output,
                        status="unread",
                        source_channel="scheduled_task",
                        inbox_metadata={"task_metadata": metadata, "delivery_channel": self._get(task, "delivery_channel")},
                    )
                    if self._get(task, "source_channel") == "telegram" and self._get(task, "telegram_chat_id") and bot_client is not None:
                        bot_client.send_message(chat_id=str(self._get(task, "telegram_chat_id")), text=output)
                finished = datetime.utcnow()
                self.repository.finish_run(run=run, status="success", output=output, error=None, metadata=metadata, now=finished)
                next_run_at, status = self._next_after_success(task=task, finished_at=finished)
                self.repository.mark_task_success(task=task, next_run_at=next_run_at, status=status, now=finished)
                executed += 1
            except Exception as exc:
                finished = datetime.utcnow()
                error = str(exc)
                self.repository.finish_run(run=run, status="failed", output=None, error=error, metadata={}, now=finished)
                self.repository.record_inbox(
                    user_id=str(self._get(task, "user_id")),
                    task_id=str(self._get(task, "id")),
                    task_run_id=str(self._get(run, "id")),
                    title=f"{self._get(task, 'title')} 执行失败",
                    content=f"定时任务执行失败：{error}",
                    status="unread",
                    source_channel="scheduled_task",
                    inbox_metadata={"error": error},
                )
                self.repository.mark_task_failed(task=task, error=error, now=finished)
        return executed

    async def _execute_task_with_chat(self, *, task: Any) -> tuple[str, dict[str, Any]]:
        from app.repositories.chat_session_repository import ChatSessionRepository
        from app.services.chat_service import ChatService

        repository = ChatSessionRepository(self.repository.db)
        service = ChatService(repository)
        message = f"执行定时任务：{self._get(task, 'instruction')}"
        session_id = str(self._get(task, "source_session_id")) if self._get(task, "source_session_id") else None
        deltas: list[str] = []
        full_content = ""
        metadata: dict[str, Any] = {}
        # skip_scheduled_task_detection 防止“执行定时任务：每天提醒我”再次递归创建任务。
        async for event in service.stream_events(
            user_id=str(self._get(task, "user_id")),
            message=message,
            session_id=session_id,
            action="send",
            skip_scheduled_task_detection=True,
        ):
            if event.get("type") == "delta":
                deltas.append(str(event.get("content_delta") or ""))
            if event.get("type") == "end":
                full_content = str(event.get("full_content") or "")
                metadata = dict(event.get("metadata") or {})
        return full_content or "".join(deltas) or "定时任务已执行，但没有生成有效内容。", {
            "tool_calls_summary": metadata.get("tool_calls_summary") or [],
            "agent_run_id": metadata.get("agent_run_id"),
            "request_id": metadata.get("request_id"),
            "model": metadata.get("model"),
            "provider": metadata.get("provider"),
        }

    def _next_after_success(self, *, task: Any, finished_at: datetime) -> tuple[datetime | None, str]:
        schedule_type = self._get(task, "schedule_type")
        schedule_value = self._get(task, "schedule_value") or {}
        if schedule_type == "once":
            return None, "completed"
        if schedule_type == "interval":
            seconds = int(schedule_value.get("seconds") or 0)
            return finished_at + timedelta(seconds=max(seconds, 1)), "enabled"
        if schedule_type == "cron":
            expr = str(schedule_value.get("cron_expr") or "")
            local_now = self._utc_to_local(finished_at, self._get(task, "timezone") or settings.telegram_timezone)
            next_local = self.detector._next_cron_run(expr, local_now)
            return self.detector._to_utc_naive(next_local, timezone_name=self._get(task, "timezone") or settings.telegram_timezone), "enabled"
        return None, "completed"

    def _format_task_list(self, tasks: list[Any]) -> str:
        if not tasks:
            return "当前没有定时任务。你可以直接说：明天上午 9 点提醒我检查投递状态。"
        lines = ["任务列表："]
        for task in tasks:
            task_id = str(self._get(task, "id"))[:8]
            lines.append(
                f"- {task_id} · {self._get(task, 'title')} · {self._status_label(self._get(task, 'status'))} · 下次 {self._format_local_time(self._get(task, 'next_run_at'), self._get(task, 'timezone'))}"
            )
        return "\n".join(lines)

    def list_tasks(self, *, user_id: str, limit: int = 30) -> dict[str, Any]:
        tasks = self.repository.list_tasks(user_id=user_id, limit=limit)
        return {"total": len(tasks), "items": [self.serialize_task(task) for task in tasks]}

    def update_task_status(self, *, user_id: str, task_id: str, status: str) -> dict[str, Any] | None:
        task = self.repository.find_task(user_id=user_id, selector=task_id)
        if task is None:
            return None
        updated = self.repository.update_status(task=task, status=status)
        return self.serialize_task(updated)

    def list_runs(self, *, user_id: str, task_id: str, limit: int = 20) -> dict[str, Any]:
        runs = self.repository.list_runs(user_id=user_id, task_id=task_id, limit=limit)
        return {"total": len(runs), "items": [self.serialize_run(run) for run in runs]}

    def list_inbox(self, *, user_id: str, limit: int = 30) -> dict[str, Any]:
        items = self.repository.list_inbox(user_id=user_id, limit=limit)
        return {"total": len(items), "items": [self.serialize_inbox(item) for item in items]}

    def mark_inbox_read(self, *, user_id: str, inbox_id: str) -> dict[str, Any] | None:
        item = self.repository.mark_inbox_read(user_id=user_id, inbox_id=inbox_id, now=datetime.utcnow())
        return self.serialize_inbox(item) if item is not None else None

    def serialize_task(self, task: Any) -> dict[str, Any]:
        return {
            "task_id": str(self._get(task, "id")),
            "title": self._get(task, "title"),
            "instruction": self._get(task, "instruction"),
            "status": self._get(task, "status"),
            "schedule_type": self._get(task, "schedule_type"),
            "schedule_value": self._get(task, "schedule_value") or {},
            "schedule_label": self._schedule_label(task),
            "timezone": self._get(task, "timezone"),
            "next_run_at": self._iso(self._get(task, "next_run_at")),
            "next_run_at_local": self._format_local_time(self._get(task, "next_run_at"), self._get(task, "timezone")),
            "last_run_at": self._iso(self._get(task, "last_run_at")),
            "source_channel": self._get(task, "source_channel"),
            "delivery_channel": self._get(task, "delivery_channel"),
            "deliver": bool(self._get(task, "deliver")),
            "last_error": self._get(task, "last_error"),
            "created_at": self._iso(self._get(task, "created_at")),
            "updated_at": self._iso(self._get(task, "updated_at")),
        }

    def serialize_run(self, run: Any) -> dict[str, Any]:
        return {
            "run_id": str(self._get(run, "id")),
            "task_id": str(self._get(run, "task_id")),
            "status": self._get(run, "status"),
            "output": self._get(run, "output"),
            "error": self._get(run, "error"),
            "metadata": self._get(run, "run_metadata") or self._get(run, "metadata") or {},
            "started_at": self._iso(self._get(run, "started_at")),
            "finished_at": self._iso(self._get(run, "finished_at")),
        }

    def serialize_inbox(self, item: Any) -> dict[str, Any]:
        return {
            "inbox_id": str(self._get(item, "id")),
            "task_id": str(self._get(item, "task_id")) if self._get(item, "task_id") else None,
            "task_run_id": str(self._get(item, "task_run_id")) if self._get(item, "task_run_id") else None,
            "title": self._get(item, "title"),
            "content": self._get(item, "content"),
            "status": self._get(item, "status"),
            "source_channel": self._get(item, "source_channel"),
            "metadata": self._get(item, "inbox_metadata") or self._get(item, "metadata") or {},
            "read_at": self._iso(self._get(item, "read_at")),
            "created_at": self._iso(self._get(item, "created_at")),
        }

    def _task_metadata(self, task: Any, *, scheduled_task_action: str) -> dict[str, Any]:
        return {
            "scheduled_task_action": scheduled_task_action,
            "scheduled_task_id": str(self._get(task, "id")),
            "schedule_summary": self._schedule_label(task),
            "next_run_at": self._iso(self._get(task, "next_run_at")),
            "task_inbox_id": None,
            "tool_calls_summary": [],
        }

    def _schedule_label(self, task: Any) -> str:
        schedule_type = self._get(task, "schedule_type")
        value = self._get(task, "schedule_value") or {}
        if schedule_type == "once":
            return "单次执行"
        if schedule_type == "interval":
            seconds = int(value.get("seconds") or 0)
            if seconds % 3600 == 0:
                return f"每 {seconds // 3600} 小时"
            if seconds % 60 == 0:
                return f"每 {seconds // 60} 分钟"
            return f"每 {seconds} 秒"
        if schedule_type == "cron":
            return f"Cron {value.get('cron_expr')}"
        return str(schedule_type or "未知")

    @staticmethod
    def _get(item: Any, key: str) -> Any:
        if isinstance(item, dict):
            return item.get(key)
        return getattr(item, key, None)

    @staticmethod
    def _iso(value: Any) -> str | None:
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    @staticmethod
    def _status_label(status: str | None) -> str:
        return {"enabled": "启用", "paused": "暂停", "cancelled": "已取消", "completed": "已完成", "running": "执行中"}.get(str(status), str(status))

    @staticmethod
    def _action_label(action: str) -> str:
        return {"cancel": "取消", "pause": "暂停", "resume": "恢复"}.get(action, "更新")

    @staticmethod
    def _utc_to_local(value: datetime, timezone_name: str) -> datetime:
        try:
            tz = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            tz = ZoneInfo("Asia/Shanghai")
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(tz).replace(tzinfo=None)

    def _format_local_time(self, value: Any, timezone_name: str | None) -> str:
        if value is None:
            return "暂无"
        if not isinstance(value, datetime):
            return str(value)
        local_value = self._utc_to_local(value, timezone_name or settings.telegram_timezone)
        return local_value.strftime("%Y-%m-%d %H:%M")
