from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from app.services.scheduled_task_service import ScheduledTaskService
from app.repositories.scheduled_task_repository import ScheduledTaskRepository


class FakeTaskRepository:
    def __init__(self) -> None:
        self.created = []
        self.tasks = []
        self.inbox = []
        self.runs = []

    def create_task(self, **kwargs):
        task = {"id": str(uuid4()), **kwargs}
        self.created.append(task)
        self.tasks.append(task)
        return task

    def list_tasks(self, *, user_id: str, limit: int = 30):
        return [task for task in self.tasks if task["user_id"] == user_id][:limit]

    def find_task(self, *, user_id: str, selector: str):
        for task in self.tasks:
            if task["user_id"] == user_id and str(task["id"]).startswith(selector):
                return task
        return None

    def update_status(self, *, task, status: str):
        task["status"] = status
        return task

    def record_inbox(self, **kwargs):
        item = {"id": str(uuid4()), **kwargs}
        self.inbox.append(item)
        return item

    def claim_due_tasks(self, *, now: datetime, limit: int = 5):
        due = []
        for task in self.tasks:
            if task["status"] == "enabled" and task["next_run_at"] and task["next_run_at"] <= now:
                task["status"] = "running"
                due.append(task)
        return due[:limit]

    def create_run(self, *, task, now: datetime):
        run = {"id": str(uuid4()), "task_id": task["id"], "user_id": task["user_id"], "started_at": now, "status": "running"}
        self.runs.append(run)
        return run

    def finish_run(self, *, run, status: str, output: str | None, error: str | None, metadata: dict | None, now: datetime):
        run.update({"status": status, "output": output, "error": error, "metadata": metadata or {}, "finished_at": now})
        return run

    def mark_task_success(self, *, task, next_run_at, status: str, now: datetime):
        task.update({"next_run_at": next_run_at, "status": status, "last_run_at": now})
        return task

    def mark_task_failed(self, *, task, error: str, now: datetime):
        task.update({"status": "enabled", "last_error": error})
        return task


def test_service_creates_task_from_chat_message() -> None:
    repository = FakeTaskRepository()
    service = ScheduledTaskService(repository=repository)
    now = datetime(2026, 6, 5, 10, 0, 0)

    result = service.handle_chat_message(
        user_id="user-1",
        message="明天上午 9 点提醒我看投递状态",
        session_id="session-1",
        channel="web",
        now=now,
    )

    assert result.handled is True
    assert result.action == "create"
    assert result.task is not None
    assert result.task["instruction"] == "看投递状态"
    assert result.task["status"] == "enabled"
    assert result.task["delivery_channel"] == "inbox"
    assert "已创建" in result.reply


def test_service_creates_telegram_task_with_visible_delivery_note() -> None:
    repository = FakeTaskRepository()
    service = ScheduledTaskService(repository=repository)
    now = datetime(2026, 6, 8, 19, 30, 0)

    result = service.handle_chat_message(
        user_id="user-1",
        message="3分钟后给我发送java的三条岗位信息",
        session_id="session-1",
        channel="telegram",
        telegram_chat_id="6219522108",
        now=now,
    )

    assert result.handled is True
    assert result.task["delivery_channel"] == "telegram"
    assert result.task["telegram_chat_id"] == "6219522108"
    assert "会直接发到当前 Telegram 聊天" in result.reply


def test_due_telegram_task_sends_result_back_to_chat(monkeypatch) -> None:
    class FakeBotClient:
        def __init__(self):
            self.sent: list[tuple[str, str]] = []

        def send_message(self, *, chat_id: str, text: str):
            self.sent.append((chat_id, text))
            return type("Result", (), {"ok": True, "error": None})()

    repository = FakeTaskRepository()
    service = ScheduledTaskService(repository=repository)
    now = datetime(2026, 6, 8, 19, 30, 0)
    task_result = service.handle_chat_message(
        user_id="user-1",
        message="1分钟后给我发送java的三条岗位信息",
        session_id="session-1",
        channel="telegram",
        telegram_chat_id="6219522108",
        now=now,
    )
    task_result.task["next_run_at"] = now

    async def fake_execute_task_with_chat(*, task):
        return "Java 岗位 1、Java 岗位 2、Java 岗位 3", {"source": "test"}

    monkeypatch.setattr(service, "_execute_task_with_chat", fake_execute_task_with_chat)
    bot_client = FakeBotClient()

    executed = __import__("asyncio").run(service.execute_due_tasks(now=now, bot_client=bot_client))

    assert executed == 1
    assert bot_client.sent == [("6219522108", "Java 岗位 1、Java 岗位 2、Java 岗位 3")]
    assert repository.inbox[0]["content"] == "Java 岗位 1、Java 岗位 2、Java 岗位 3"


def test_service_lists_and_cancels_tasks() -> None:
    repository = FakeTaskRepository()
    service = ScheduledTaskService(repository=repository)
    now = datetime(2026, 6, 5, 10, 0, 0)

    create = service.handle_chat_message(user_id="user-1", message="每 30 分钟检查一次岗位", session_id="s1", channel="web", now=now)
    task_id = create.task["id"]

    listed = service.handle_chat_message(user_id="user-1", message="列出我的定时任务", session_id="s1", channel="web", now=now)
    cancelled = service.handle_chat_message(user_id="user-1", message=f"取消任务 {task_id[:8]}", session_id="s1", channel="web", now=now)

    assert "检查一次岗位" in listed.reply
    assert cancelled.action == "cancel"
    assert create.task["status"] == "cancelled"


def test_repository_contract_keeps_executor_safe_allowlist() -> None:
    assert set(ScheduledTaskService.ALLOWED_TASK_TOOLS) == {
        "chat_answer",
        "resume_profile",
        "job_search",
        "application_list",
        "knowledge_search",
        "telegram_send",
    }
    assert "shell" not in ScheduledTaskService.ALLOWED_TASK_TOOLS
    assert "auto_apply" not in ScheduledTaskService.ALLOWED_TASK_TOOLS
