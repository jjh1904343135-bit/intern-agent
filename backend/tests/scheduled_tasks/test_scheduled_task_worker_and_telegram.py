from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.tasks import telegram_tasks
from app.services.telegram_bridge_service import TelegramBridgeService, TelegramHandleResult


@dataclass
class FakeSend:
    chat_id: str
    text: str


class FakeBotClient:
    def __init__(self) -> None:
        self.sent: list[FakeSend] = []

    def send_message(self, *, chat_id: str, text: str):
        self.sent.append(FakeSend(chat_id=chat_id, text=text))
        return {"ok": True}


def test_worker_iteration_runs_scheduled_tasks_even_when_telegram_disabled(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(telegram_tasks, "poll_telegram_updates_once", lambda: calls.append("poll") or 0)
    monkeypatch.setattr(telegram_tasks, "maybe_start_proactive_notifications", lambda: calls.append("proactive") or False)
    monkeypatch.setattr(telegram_tasks, "run_scheduled_tasks_once", lambda: calls.append("scheduled") or 1)

    telegram_tasks.run_worker_iteration()

    assert calls == ["poll", "proactive", "scheduled"]


def test_telegram_tasks_commands_are_handled(monkeypatch) -> None:
    captured: list[tuple[str, str]] = []

    def fake_handle_command(self, *, user_id: str, message: str, session_id: str | None, channel: str, telegram_chat_id: str | None = None):
        captured.append((message, telegram_chat_id or ""))
        return type("Result", (), {"handled": True, "reply": "任务列表：\n- 每天 9 点检查投递", "action": "list"})()

    monkeypatch.setattr("app.services.scheduled_task_service.ScheduledTaskService.handle_chat_message", fake_handle_command)

    bridge = TelegramBridgeService(db=None, bot_client=FakeBotClient(), allowed_values={"42"})
    reply = bridge._handle_tasks_command(user_id="user-1", chat_id="42")

    assert reply.processed is True
    assert reply.message == "tasks"
    assert captured == [("列出我的定时任务", "42")]
    assert bridge.bot_client.sent[-1].text.startswith("任务列表")
