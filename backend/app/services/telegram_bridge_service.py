from __future__ import annotations

from datetime import datetime
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories.chat_session_repository import ChatSessionRepository
from app.repositories.notification_repository import TelegramAccountRepository, TelegramBindCodeRepository
from app.repositories.user_repository import UserRepository
from app.services.assistant_memory_command_service import AssistantMemoryCommandService
from app.services.telegram_client import TelegramBotClient

STOPPED_TEXT = "\u5df2\u6682\u505c\u9752\u7a0b AI \u7684 Telegram \u6d88\u606f\u3002"
NO_DEFAULT_USER_TEXT = "\u8bf7\u5148\u5728 .env \u914d\u7f6e TELEGRAM_DEFAULT_USER_EMAIL\uff0c\u518d\u91cd\u65b0\u53d1\u9001 /start\u3002"
BOUND_TEXT = "\u5df2\u8fde\u63a5\u9752\u7a0b AI\u3002\u4f60\u53ef\u4ee5\u76f4\u63a5\u53d1\u6d88\u606f\u7ed9\u6c42\u804c\u52a9\u624b\uff0c\u4e5f\u4f1a\u6536\u5230\u6709\u8282\u5236\u7684\u4e3b\u52a8\u63d0\u9192\u3002"
NOT_BOUND_TEXT = "\u8fd9\u4e2a Telegram \u4f1a\u8bdd\u8fd8\u6ca1\u6709\u7ed1\u5b9a\u7528\u6237\u3002\u8bf7\u5148\u5728\u7f51\u9875\u751f\u6210\u7ed1\u5b9a\u7801\uff0c\u7136\u540e\u53d1\u9001 /bind \u7ed1\u5b9a\u7801\u3002"
EMPTY_REPLY_TEXT = "\u8fd9\u8f6e\u6ca1\u6709\u751f\u6210\u6709\u6548\u56de\u590d\u3002"
NEW_SESSION_TEXT = "\u5df2\u65b0\u5f00 Telegram \u4f1a\u8bdd\u3002\u4e0b\u4e00\u6761\u6d88\u606f\u4f1a\u7ee7\u7eed\u8fd9\u4e2a\u65b0\u4f1a\u8bdd\u3002"
NO_CURRENT_SESSION_TEXT = "\u5f53\u524d\u8fd8\u6ca1\u6709 Telegram \u4f1a\u8bdd\u3002\u53d1\u9001 /new \u65b0\u5f00\u4e00\u4e2a\uff0c\u6216\u76f4\u63a5\u53d1\u6d88\u606f\u8ba9\u7cfb\u7edf\u81ea\u52a8\u521b\u5efa\u3002"
NO_RECENT_SESSIONS_TEXT = "\u6682\u65f6\u6ca1\u6709\u53ef\u5207\u6362\u7684\u804a\u5929\u4f1a\u8bdd\u3002"
SESSION_NOT_FOUND_TEXT = "\u6ca1\u627e\u5230\u8fd9\u4e2a\u4f1a\u8bdd\uff0c\u53ef\u4ee5\u53d1\u9001 /sessions \u67e5\u770b\u6700\u8fd1\u4f1a\u8bdd\u3002"
BIND_CODE_REQUIRED_TEXT = "\u8bf7\u5e26\u4e0a\u7f51\u9875\u751f\u6210\u7684\u7ed1\u5b9a\u7801\uff0c\u683c\u5f0f\uff1a/bind ABCD2345\u3002"
INVALID_BIND_CODE_TEXT = "\u7ed1\u5b9a\u7801\u65e0\u6548\u6216\u5df2\u8fc7\u671f\uff0c\u8bf7\u56de\u5230\u7f51\u9875\u91cd\u65b0\u751f\u6210\u4e00\u4e2a\u7ed1\u5b9a\u7801\u3002"


@dataclass(frozen=True)
class TelegramInboundMessage:
    update_id: int
    message_id: int
    chat_id: str
    sender_id: str
    username: str | None
    first_name: str | None
    text: str
    message_timestamp: int


@dataclass
class TelegramHandleResult:
    processed: bool
    message: str
    user_id: str | None = None


@dataclass(frozen=True)
class TelegramChatRunResult:
    reply: str
    session_id: str | None


def parse_telegram_update(update: dict[str, Any]) -> TelegramInboundMessage | None:
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    text = str(message.get("text") or "").strip()
    if not text:
        return None
    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    chat_id = chat.get("id")
    sender_id = sender.get("id")
    if chat_id is None or sender_id is None:
        return None
    return TelegramInboundMessage(
        update_id=int(update.get("update_id") or 0),
        message_id=int(message.get("message_id") or 0),
        chat_id=str(chat_id),
        sender_id=str(sender_id),
        username=sender.get("username"),
        first_name=sender.get("first_name"),
        text=text,
        message_timestamp=int(message.get("date") or 0),
    )


def is_allowed_telegram_sender(
    *,
    chat_id: str,
    username: str | None,
    allowed_values: set[str],
    allow_empty_allowlist: bool = False,
) -> bool:
    if not allowed_values:
        return allow_empty_allowlist
    normalized = {value.lower().lstrip("@") for value in allowed_values if value.strip()}
    return str(chat_id).lower() in normalized or bool(username and username.lower().lstrip("@") in normalized)


class TelegramBridgeService:
    def __init__(
        self,
        *,
        db: Session,
        bot_client: TelegramBotClient,
        allowed_values: set[str],
        default_user_email: str | None = None,
        allow_empty_allowlist: bool = False,
    ):
        self.db = db
        self.bot_client = bot_client
        self.allowed_values = allowed_values
        self.default_user_email = default_user_email
        self.allow_empty_allowlist = allow_empty_allowlist

    async def handle_update(self, update: dict[str, Any]) -> TelegramHandleResult:
        inbound = parse_telegram_update(update)
        if inbound is None:
            return TelegramHandleResult(processed=False, message="ignored")
        command, command_args = _parse_telegram_command(inbound.text)
        is_bind_code_attempt = command in {"/start", "/bind"} and bool(command_args.strip())
        # 未绑定用户只允许走绑定码流程；普通消息必须先通过白名单或开发兜底。
        sender_allowed = is_allowed_telegram_sender(
            chat_id=inbound.chat_id,
            username=inbound.username,
            allowed_values=self.allowed_values,
            allow_empty_allowlist=self.allow_empty_allowlist,
        )
        if not sender_allowed and not is_bind_code_attempt:
            return TelegramHandleResult(processed=False, message="unauthorized")

        account_repository = TelegramAccountRepository(self.db)
        account = account_repository.get_by_chat_id(chat_id=inbound.chat_id)

        if command == "/stop":
            if account is not None:
                account_repository.disable(account=account)
            self.bot_client.send_message(chat_id=inbound.chat_id, text=STOPPED_TEXT)
            return TelegramHandleResult(processed=True, message="stopped")

        if command == "/bind":
            if command_args.strip():
                return self._bind_account_by_code(inbound=inbound, code=command_args)
            self.bot_client.send_message(chat_id=inbound.chat_id, text=BIND_CODE_REQUIRED_TEXT)
            return TelegramHandleResult(processed=False, message="bind_code_required")

        if command == "/start" and command_args.strip():
            return self._bind_account_by_code(inbound=inbound, code=command_args)

        if command == "/start":
            account = self._bind_default_account(inbound=inbound)
            if account is None:
                self.bot_client.send_message(chat_id=inbound.chat_id, text=NO_DEFAULT_USER_TEXT)
                return TelegramHandleResult(processed=False, message="no_default_user")
            self.bot_client.send_message(chat_id=inbound.chat_id, text=BOUND_TEXT)
            return TelegramHandleResult(processed=True, message="bound", user_id=str(account.user_id))

        if account is None or not account.enabled:
            self.bot_client.send_message(chat_id=inbound.chat_id, text=NOT_BOUND_TEXT)
            return TelegramHandleResult(processed=False, message="not_bound")

        if command == "/new":
            return await self._handle_new_session_command(account=account, inbound=inbound, command_args=command_args)
        if command == "/current":
            return self._handle_current_session_command(account=account, inbound=inbound)
        if command == "/sessions":
            return self._handle_sessions_command(account=account, inbound=inbound)
        if command == "/use":
            return self._handle_use_session_command(account=account, inbound=inbound, command_args=command_args)
        if command == "/tasks":
            return self._handle_tasks_command(user_id=str(account.user_id), chat_id=inbound.chat_id)
        if command in {"/dream", "/dream-log", "/dream-restore"}:
            return self._handle_memory_command(user_id=str(account.user_id), chat_id=inbound.chat_id, text=inbound.text)
        if command == "/cancel_task":
            return self._handle_task_action_command(
                user_id=str(account.user_id),
                chat_id=inbound.chat_id,
                action_text=f"取消任务 {command_args}",
            )
        if command == "/pause_task":
            return self._handle_task_action_command(
                user_id=str(account.user_id),
                chat_id=inbound.chat_id,
                action_text=f"暂停任务 {command_args}",
            )
        if command == "/resume_task":
            return self._handle_task_action_command(
                user_id=str(account.user_id),
                chat_id=inbound.chat_id,
                action_text=f"恢复任务 {command_args}",
            )

        # 普通 Telegram 消息复用网页 ChatService；account.chat_session_id 保证手机端连续会话。
        chat_result = await self._run_chat(
            user_id=str(account.user_id),
            message=inbound.text,
            session_id=str(account.chat_session_id) if account.chat_session_id else None,
            telegram_chat_id=inbound.chat_id,
        )
        self.bot_client.send_message(chat_id=inbound.chat_id, text=chat_result.reply)
        account_repository.mark_seen(
            account=account,
            username=inbound.username,
            first_name=inbound.first_name,
            chat_session_id=chat_result.session_id,
        )
        return TelegramHandleResult(processed=True, message="chat_replied", user_id=str(account.user_id))

    def _bind_default_account(self, *, inbound: TelegramInboundMessage):
        if not self.default_user_email:
            return None
        user = UserRepository(self.db).get_by_email(self.default_user_email)
        if user is None:
            return None
        return TelegramAccountRepository(self.db).upsert(
            user_id=str(user.id),
            chat_id=inbound.chat_id,
            username=inbound.username,
            first_name=inbound.first_name,
        )

    def _bind_account_by_code(self, *, inbound: TelegramInboundMessage, code: str) -> TelegramHandleResult:
        bind_code = TelegramBindCodeRepository(self.db).consume(code=code, now=datetime.utcnow())
        if bind_code is None:
            self.bot_client.send_message(chat_id=inbound.chat_id, text=INVALID_BIND_CODE_TEXT)
            return TelegramHandleResult(processed=False, message="invalid_bind_code")
        account = TelegramAccountRepository(self.db).upsert(
            user_id=str(bind_code.user_id),
            chat_id=inbound.chat_id,
            username=inbound.username,
            first_name=inbound.first_name,
        )
        self.bot_client.send_message(chat_id=inbound.chat_id, text=BOUND_TEXT)
        return TelegramHandleResult(processed=True, message="bound", user_id=str(account.user_id))

    async def _run_chat(
        self,
        *,
        user_id: str,
        message: str,
        session_id: str | None = None,
        telegram_chat_id: str | None = None,
    ) -> TelegramChatRunResult:
        from app.repositories.chat_session_repository import ChatSessionRepository
        from app.services.chat_service import ChatService

        service = ChatService(ChatSessionRepository(self.db))
        full_content = ""
        deltas: list[str] = []
        conversation_id: str | None = None
        async for event in service.stream_events(
            user_id=user_id,
            message=message,
            session_id=session_id,
            action="send",
            channel="telegram",
            telegram_chat_id=telegram_chat_id,
        ):
            if event.get("conversation_id"):
                conversation_id = str(event.get("conversation_id"))
            if event.get("type") == "delta":
                deltas.append(str(event.get("content_delta") or ""))
            if event.get("type") == "end":
                full_content = str(event.get("full_content") or "")
        return TelegramChatRunResult(
            reply=full_content or "".join(deltas) or EMPTY_REPLY_TEXT,
            session_id=conversation_id or session_id,
        )

    async def _handle_new_session_command(
        self,
        *,
        account,
        inbound: TelegramInboundMessage,
        command_args: str,
    ) -> TelegramHandleResult:
        account_repository = TelegramAccountRepository(self.db)
        # /new 会显式切换 sticky chat_session_id，后续手机消息继续这个新会话。
        session = ChatSessionRepository(self.db).create(
            user_id=str(account.user_id),
            messages=[],
            agent_states={"supervisor": "ready"},
            last_agent="supervisor",
            token_count=0,
        )
        session_id = str(session.id)
        account_repository.mark_seen(
            account=account,
            username=inbound.username,
            first_name=inbound.first_name,
            chat_session_id=session_id,
        )
        first_message = command_args.strip()
        if not first_message:
            self.bot_client.send_message(chat_id=inbound.chat_id, text=NEW_SESSION_TEXT)
            return TelegramHandleResult(processed=True, message="new_session", user_id=str(account.user_id))

        chat_result = await self._run_chat(
            user_id=str(account.user_id),
            message=first_message,
            session_id=session_id,
            telegram_chat_id=inbound.chat_id,
        )
        self.bot_client.send_message(chat_id=inbound.chat_id, text=chat_result.reply)
        account_repository.mark_seen(
            account=account,
            username=inbound.username,
            first_name=inbound.first_name,
            chat_session_id=chat_result.session_id or session_id,
        )
        return TelegramHandleResult(processed=True, message="chat_replied", user_id=str(account.user_id))

    def _handle_current_session_command(self, *, account, inbound: TelegramInboundMessage) -> TelegramHandleResult:
        session_id = str(account.chat_session_id) if account.chat_session_id else None
        if not session_id:
            self.bot_client.send_message(chat_id=inbound.chat_id, text=NO_CURRENT_SESSION_TEXT)
            return TelegramHandleResult(processed=True, message="no_current_session", user_id=str(account.user_id))
        session = ChatSessionRepository(self.db).get_by_id(session_id=session_id, user_id=str(account.user_id))
        if session is None:
            self.bot_client.send_message(chat_id=inbound.chat_id, text=NO_CURRENT_SESSION_TEXT)
            return TelegramHandleResult(processed=True, message="no_current_session", user_id=str(account.user_id))
        self.bot_client.send_message(chat_id=inbound.chat_id, text=_format_current_session(session))
        return TelegramHandleResult(processed=True, message="current_session", user_id=str(account.user_id))

    def _handle_sessions_command(self, *, account, inbound: TelegramInboundMessage) -> TelegramHandleResult:
        sessions = ChatSessionRepository(self.db).list_by_user_id(user_id=str(account.user_id), limit=5)
        if not sessions:
            self.bot_client.send_message(chat_id=inbound.chat_id, text=NO_RECENT_SESSIONS_TEXT)
            return TelegramHandleResult(processed=True, message="sessions", user_id=str(account.user_id))
        active_session_id = str(account.chat_session_id) if account.chat_session_id else ""
        lines = ["\u6700\u8fd1\u4f1a\u8bdd\uff1a"]
        for session in sessions:
            marker = "*" if str(session.id) == active_session_id else "-"
            lines.append(f"{marker} {str(session.id)[:8]} {_session_title(session)} ({_session_turn_count(session)} turns)")
        self.bot_client.send_message(chat_id=inbound.chat_id, text="\n".join(lines))
        return TelegramHandleResult(processed=True, message="sessions", user_id=str(account.user_id))

    def _handle_use_session_command(
        self,
        *,
        account,
        inbound: TelegramInboundMessage,
        command_args: str,
    ) -> TelegramHandleResult:
        selector = command_args.strip()
        session = self._find_owned_session(user_id=str(account.user_id), selector=selector)
        if session is None:
            self.bot_client.send_message(chat_id=inbound.chat_id, text=SESSION_NOT_FOUND_TEXT)
            return TelegramHandleResult(processed=False, message="session_not_found", user_id=str(account.user_id))
        TelegramAccountRepository(self.db).mark_seen(
            account=account,
            username=inbound.username,
            first_name=inbound.first_name,
            chat_session_id=str(session.id),
        )
        self.bot_client.send_message(
            chat_id=inbound.chat_id,
            text=f"\u5df2\u5207\u6362\u5230 {str(session.id)[:8]} {_session_title(session)}",
        )
        return TelegramHandleResult(processed=True, message="session_switched", user_id=str(account.user_id))

    def _handle_tasks_command(self, *, user_id: str, chat_id: str) -> TelegramHandleResult:
        from app.repositories.scheduled_task_repository import ScheduledTaskRepository
        from app.services.scheduled_task_service import ScheduledTaskService

        result = ScheduledTaskService(repository=ScheduledTaskRepository(self.db)).handle_chat_message(
            user_id=user_id,
            message="列出我的定时任务",
            session_id=None,
            channel="telegram",
            telegram_chat_id=chat_id,
        )
        self.bot_client.send_message(chat_id=chat_id, text=result.reply)
        return TelegramHandleResult(processed=True, message="tasks", user_id=user_id)

    def _handle_task_action_command(self, *, user_id: str, chat_id: str, action_text: str) -> TelegramHandleResult:
        from app.repositories.scheduled_task_repository import ScheduledTaskRepository
        from app.services.scheduled_task_service import ScheduledTaskService

        result = ScheduledTaskService(repository=ScheduledTaskRepository(self.db)).handle_chat_message(
            user_id=user_id,
            message=action_text,
            session_id=None,
            channel="telegram",
            telegram_chat_id=chat_id,
        )
        self.bot_client.send_message(chat_id=chat_id, text=result.reply)
        return TelegramHandleResult(processed=True, message=result.action or "task_action", user_id=user_id)

    def _handle_memory_command(self, *, user_id: str, chat_id: str, text: str) -> TelegramHandleResult:
        result = AssistantMemoryCommandService().handle(user_id=user_id, message=text)
        if result is None:
            self.bot_client.send_message(chat_id=chat_id, text="Unknown memory command.")
            return TelegramHandleResult(processed=False, message="unknown_memory_command", user_id=user_id)
        self.bot_client.send_message(chat_id=chat_id, text=result.reply)
        return TelegramHandleResult(processed=True, message=result.command, user_id=user_id)

    def _find_owned_session(self, *, user_id: str, selector: str):
        if not selector:
            return None
        repository = ChatSessionRepository(self.db)
        try:
            UUID(selector)
        except ValueError:
            exact = None
        else:
            exact = repository.get_by_id(session_id=selector, user_id=user_id)
            if exact is not None:
                return exact
        matches = [session for session in repository.list_by_user_id(user_id=user_id, limit=30) if str(session.id).startswith(selector)]
        return matches[0] if len(matches) == 1 else None


def _parse_telegram_command(text: str) -> tuple[str | None, str]:
    stripped = (text or "").strip()
    if not stripped.startswith("/"):
        return None, ""
    parts = stripped.split(maxsplit=1)
    command = parts[0].split("@", 1)[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    return command, args


def _session_title(session) -> str:
    messages = list(session.messages or [])
    first_user = next((str(item.get("content") or "") for item in messages if item.get("role") == "user"), "")
    return first_user[:32] or "\u65b0\u5bf9\u8bdd"


def _session_turn_count(session) -> int:
    return len([item for item in list(session.messages or []) if item.get("role") == "user"])


def _format_current_session(session) -> str:
    return f"\u5f53\u524d\u4f1a\u8bdd\uff1a{str(session.id)[:8]} {_session_title(session)} ({_session_turn_count(session)} turns)"
