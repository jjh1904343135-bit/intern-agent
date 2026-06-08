from __future__ import annotations

import threading
from pathlib import Path

from app.tasks import telegram_tasks


def test_worker_iteration_polls_even_when_proactive_scheduler_fails(monkeypatch) -> None:
    calls: list[str] = []

    def fake_poll() -> int:
        calls.append("poll")
        return 1

    def fake_start_proactive() -> bool:
        calls.append("proactive")
        raise RuntimeError("proactive failed")

    monkeypatch.setattr(telegram_tasks, "poll_telegram_updates_once", fake_poll)
    monkeypatch.setattr(telegram_tasks, "maybe_start_proactive_notifications", fake_start_proactive)

    telegram_tasks.run_worker_iteration()

    assert calls == ["poll", "proactive"]


def test_proactive_notifications_run_in_background(monkeypatch) -> None:
    started = threading.Event()
    release = threading.Event()

    def fake_run_proactive_notifications_once(*, force: bool = False) -> int:
        assert force is True
        started.set()
        release.wait(timeout=5)
        return 0

    monkeypatch.setattr(telegram_tasks.settings, "telegram_enabled", True)
    monkeypatch.setattr(telegram_tasks.settings, "telegram_bot_token", "token")
    monkeypatch.setattr(telegram_tasks.settings, "telegram_notification_tick_seconds", 300)
    monkeypatch.setattr(telegram_tasks, "run_proactive_notifications_once", fake_run_proactive_notifications_once)
    monkeypatch.setattr(telegram_tasks.time, "monotonic", lambda: 1000.0)
    monkeypatch.setattr(telegram_tasks, "_last_notification_tick_at", 0.0)
    monkeypatch.setattr(telegram_tasks, "_proactive_thread", None)

    try:
        assert telegram_tasks.maybe_start_proactive_notifications() is True
        assert started.wait(timeout=1)
        assert telegram_tasks.maybe_start_proactive_notifications() is False
    finally:
        release.set()
        thread = telegram_tasks._proactive_thread
        if thread is not None:
            thread.join(timeout=2)


def test_module_main_guard_runs_after_helpers_are_defined() -> None:
    source = Path(telegram_tasks.__file__).read_text(encoding="utf-8")

    assert source.index("def _csv_set") < source.index('if __name__ == "__main__"')
