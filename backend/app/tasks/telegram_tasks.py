from __future__ import annotations

import asyncio
import logging
import threading
import time
from pathlib import Path

from app.core.database import session_local
from app.core.providers.factory import get_provider
from app.core.settings import settings
from app.repositories.scheduled_task_repository import ScheduledTaskRepository
from app.services.proactive_notification_service import ProactiveNotificationService
from app.services.scheduled_task_service import ScheduledTaskService
from app.services.telegram_bridge_service import TelegramBridgeService
from app.services.telegram_client import TelegramBotClient
from app.services.telegram_offset_store import TelegramUpdateOffsetStore


logger = logging.getLogger(__name__)
_last_notification_tick_at = 0.0
_proactive_lock = threading.Lock()
_proactive_thread: threading.Thread | None = None


def poll_telegram_updates_once() -> int:
    if not settings.telegram_enabled or not settings.telegram_bot_token:
        return 0
    offset_store = TelegramUpdateOffsetStore(Path("/app/runtime/telegram/update_offset.txt"))
    with TelegramBotClient(token=settings.telegram_bot_token) as client:
        # offset 文件记录已处理 update，避免 worker 重启后重复回复旧消息。
        offset = offset_store.read()
        updates = client.get_updates(
            offset=offset,
            timeout_seconds=settings.telegram_poll_timeout_seconds,
            limit=settings.telegram_poll_limit,
        )
        processed = 0
        with session_local() as db:
            service = TelegramBridgeService(
                db=db,
                bot_client=client,
                allowed_values=_csv_set(settings.telegram_allowed_chat_ids),
                default_user_email=settings.telegram_default_user_email,
                allow_empty_allowlist=settings.app_env == "dev",
            )
            for update in updates:
                result = asyncio.run(service.handle_update(update))
                processed += 1 if result.processed else 0
                update_id = update.get("update_id")
                if isinstance(update_id, int):
                    offset_store.write(update_id + 1)
        return processed


def run_proactive_notifications_once(*, force: bool = False) -> int:
    if not settings.telegram_enabled or not settings.telegram_bot_token:
        return 0
    global _last_notification_tick_at
    now_monotonic = time.monotonic()
    if not force and _last_notification_tick_at and now_monotonic - _last_notification_tick_at < settings.telegram_notification_tick_seconds:
        return 0
    _last_notification_tick_at = now_monotonic
    with TelegramBotClient(token=settings.telegram_bot_token) as client:
        with session_local() as db:
            service = ProactiveNotificationService(
                db=db,
                bot_client=client,
                provider=get_provider(),
                timezone_name=settings.telegram_timezone,
                quiet_start_hour=settings.telegram_quiet_start_hour,
                quiet_end_hour=settings.telegram_quiet_end_hour,
                daily_limit=settings.telegram_daily_push_limit,
                same_type_cooldown_hours=settings.telegram_same_type_cooldown_hours,
                allowed_chat_ids=_csv_set(settings.telegram_allowed_chat_ids),
            )
            return asyncio.run(service.tick_once())


def maybe_start_proactive_notifications() -> bool:
    if not settings.telegram_enabled or not settings.telegram_bot_token:
        return False
    global _last_notification_tick_at, _proactive_thread
    now_monotonic = time.monotonic()
    with _proactive_lock:
        if _proactive_thread is not None and _proactive_thread.is_alive():
            return False
        if _last_notification_tick_at and now_monotonic - _last_notification_tick_at < settings.telegram_notification_tick_seconds:
            return False
        _last_notification_tick_at = now_monotonic
        _proactive_thread = threading.Thread(
            target=_run_proactive_notifications_safely,
            name="telegram-proactive-notifications",
            daemon=True,
        )
        _proactive_thread.start()
        return True


def _run_proactive_notifications_safely() -> None:
    try:
        run_proactive_notifications_once(force=True)
    except Exception:
        logger.exception("Telegram proactive notification tick failed")
    finally:
        global _proactive_thread
        with _proactive_lock:
            _proactive_thread = None


def run_scheduled_tasks_once() -> int:
    # 定时任务 worker 和 Telegram worker 共用进程；启用 Telegram 时额外传入 bot client 做回传。
    bot_client = None
    if settings.telegram_enabled and settings.telegram_bot_token:
        bot_client = TelegramBotClient(token=settings.telegram_bot_token)
    if bot_client is None:
        with session_local() as db:
            return asyncio.run(ScheduledTaskService(repository=ScheduledTaskRepository(db)).execute_due_tasks())
    with bot_client as client:
        with session_local() as db:
            return asyncio.run(ScheduledTaskService(repository=ScheduledTaskRepository(db)).execute_due_tasks(bot_client=client))


def run_worker_iteration() -> None:
    # 三类任务互相隔离捕获异常，避免主动推送失败拖垮用户聊天或定时任务。
    try:
        poll_telegram_updates_once()
    except Exception:
        logger.exception("Telegram polling failed")
    try:
        maybe_start_proactive_notifications()
    except Exception:
        logger.exception("Telegram proactive notification scheduler failed")
    try:
        run_scheduled_tasks_once()
    except Exception:
        logger.exception("Scheduled task runner failed")


def run_worker() -> None:
    while True:
        run_worker_iteration()
        time.sleep(settings.resume_worker_interval_seconds)


def _csv_set(value: str | None) -> set[str]:
    return {item.strip() for item in (value or "").split(",") if item.strip()}


if __name__ == "__main__":
    run_worker()
