from __future__ import annotations

from datetime import datetime

from app.services.scheduled_task_parser import ScheduledTaskIntentDetector


def test_parser_creates_once_reminder_for_tomorrow_morning() -> None:
    now = datetime(2026, 6, 5, 10, 0, 0)
    result = ScheduledTaskIntentDetector().detect("明天上午 9 点提醒我看投递状态", now=now, timezone_name="Asia/Shanghai")

    assert result.handled is True
    assert result.action == "create"
    assert result.confidence >= 0.8
    assert result.schedule_type == "once"
    assert result.next_run_at_local == "2026-06-06T09:00:00"
    assert "投递状态" in result.instruction


def test_parser_creates_interval_task() -> None:
    now = datetime(2026, 6, 5, 10, 0, 0)
    result = ScheduledTaskIntentDetector().detect("每 30 分钟检查一次岗位", now=now, timezone_name="Asia/Shanghai")

    assert result.handled is True
    assert result.action == "create"
    assert result.schedule_type == "interval"
    assert result.schedule_value == {"seconds": 1800}
    assert result.next_run_at_local == "2026-06-05T10:30:00"
    assert result.instruction == "检查一次岗位"


def test_parser_creates_relative_once_reminder_for_minutes_later() -> None:
    now = datetime(2026, 6, 5, 10, 0, 0)
    result = ScheduledTaskIntentDetector().detect("一分钟后提醒我看岗位", now=now, timezone_name="Asia/Shanghai")

    assert result.handled is True
    assert result.action == "create"
    assert result.schedule_type == "once"
    assert result.next_run_at_local == "2026-06-05T10:01:00"
    assert "看岗位" in result.instruction


def test_parser_creates_weekly_cron_task_from_natural_language() -> None:
    now = datetime(2026, 6, 5, 10, 0, 0)
    result = ScheduledTaskIntentDetector().detect("每周一早上 9 点提醒我检查投递", now=now, timezone_name="Asia/Shanghai")

    assert result.handled is True
    assert result.action == "create"
    assert result.schedule_type == "cron"
    assert result.schedule_value["cron_expr"] == "0 9 * * 1"
    assert result.next_run_at_local == "2026-06-08T09:00:00"


def test_parser_creates_workday_cron_task() -> None:
    now = datetime(2026, 6, 5, 10, 0, 0)
    result = ScheduledTaskIntentDetector().detect("工作日早上 9 点提醒我看部署日志", now=now, timezone_name="Asia/Shanghai")

    assert result.handled is True
    assert result.action == "create"
    assert result.schedule_type == "cron"
    assert result.schedule_value["cron_expr"] == "0 9 * * 1-5"
    assert result.next_run_at_local == "2026-06-08T09:00:00"


def test_parser_lists_and_cancels_tasks() -> None:
    detector = ScheduledTaskIntentDetector()

    list_result = detector.detect("列出我的定时任务", now=datetime(2026, 6, 5, 10), timezone_name="Asia/Shanghai")
    cancel_result = detector.detect("取消任务 abc123", now=datetime(2026, 6, 5, 10), timezone_name="Asia/Shanghai")

    assert list_result.handled is True
    assert list_result.action == "list"
    assert cancel_result.handled is True
    assert cancel_result.action == "cancel"
    assert cancel_result.selector == "abc123"


def test_parser_asks_clarification_for_ambiguous_reminder() -> None:
    result = ScheduledTaskIntentDetector().detect("提醒我检查简历", now=datetime(2026, 6, 5, 10), timezone_name="Asia/Shanghai")

    assert result.handled is True
    assert result.action == "clarify"
    assert "时间" in result.reply
