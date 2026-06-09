from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import text

from app.core.settings import settings
from app.core.database import session_local
from app.repositories.chat_session_repository import ChatSessionRepository
from app.repositories.notification_repository import TelegramAccountRepository, TelegramBindCodeRepository
from app.services.telegram_bridge_service import (
    BOUND_TEXT,
    STOPPED_TEXT,
    TelegramChatRunResult,
    TelegramBridgeService,
    TelegramInboundMessage,
    is_allowed_telegram_sender,
    parse_telegram_update,
)


@dataclass
class FakeSend:
    chat_id: str
    text: str


class FakeBotClient:
    def __init__(self) -> None:
        self.sent: list[FakeSend] = []

    def send_message(self, *, chat_id: str, text: str):
        self.sent.append(FakeSend(chat_id=chat_id, text=text))
        return type("Result", (), {"ok": True, "sent_count": 1, "error": None})()


def _reset_telegram_bridge_data() -> str:
    with session_local() as session:
        session.execute(text("DELETE FROM telegram_bind_codes"))
        session.execute(text("DELETE FROM telegram_accounts"))
        session.execute(text("DELETE FROM assistant_memories"))
        session.execute(text("DELETE FROM chat_sessions"))
        session.execute(text("DELETE FROM interview_sessions"))
        session.execute(text("DELETE FROM applications"))
        session.execute(text("DELETE FROM resumes"))
        session.execute(text("DELETE FROM jobs"))
        session.execute(text("DELETE FROM users"))
        user_id = session.execute(
            text(
                """
                INSERT INTO users (email, password_hash, name, quota_reset_at)
                VALUES ('telegram@example.com', 'hash', 'Telegram User', now())
                RETURNING id
                """
            )
        ).scalar_one()
        session.commit()
        return str(user_id)


def _telegram_update(*, text_value: str, chat_id: str = "42", username: str = "alice") -> dict:
    return {
        "update_id": 11,
        "message": {
            "message_id": 7,
            "date": 1770000000,
            "chat": {"id": int(chat_id), "type": "private"},
            "from": {"id": 99, "username": username, "first_name": "Alice"},
            "text": text_value,
        },
    }


def test_parse_telegram_update_returns_text_message_with_timestamp() -> None:
    update = _telegram_update(text_value="what should I do today?")

    message = parse_telegram_update(update)

    assert message == TelegramInboundMessage(
        update_id=11,
        message_id=7,
        chat_id="42",
        sender_id="99",
        username="alice",
        first_name="Alice",
        text="what should I do today?",
        message_timestamp=1770000000,
    )


def test_parse_telegram_update_ignores_non_text_messages() -> None:
    assert parse_telegram_update({"update_id": 1, "message": {"photo": []}}) is None


def test_is_allowed_telegram_sender_supports_chat_id_and_username() -> None:
    assert is_allowed_telegram_sender(chat_id="42", username="alice", allowed_values={"42"}) is True
    assert is_allowed_telegram_sender(chat_id="43", username="Alice", allowed_values={"alice"}) is True
    assert is_allowed_telegram_sender(chat_id="43", username="bob", allowed_values={"alice"}) is False
    assert is_allowed_telegram_sender(chat_id="43", username="bob", allowed_values=set()) is False
    assert is_allowed_telegram_sender(chat_id="43", username="bob", allowed_values=set(), allow_empty_allowlist=True) is True


def test_handle_update_rejects_unauthorized_sender_without_sending() -> None:
    _reset_telegram_bridge_data()
    bot = FakeBotClient()
    with session_local() as session:
        service = TelegramBridgeService(
            db=session,
            bot_client=bot,
            allowed_values={"allowed_user"},
            default_user_email="telegram@example.com",
        )

        result = asyncio.run(service.handle_update(_telegram_update(text_value="/start", username="intruder")))

    assert result.processed is False
    assert result.message == "unauthorized"
    assert bot.sent == []


def test_handle_update_binds_allowed_sender_to_default_user() -> None:
    user_id = _reset_telegram_bridge_data()
    bot = FakeBotClient()
    with session_local() as session:
        service = TelegramBridgeService(
            db=session,
            bot_client=bot,
            allowed_values={"alice"},
            default_user_email="telegram@example.com",
        )

        result = asyncio.run(service.handle_update(_telegram_update(text_value="/start")))
        account = TelegramAccountRepository(session).get_by_chat_id(chat_id="42")

    assert result.processed is True
    assert result.message == "bound"
    assert result.user_id == user_id
    assert account is not None
    assert str(account.user_id) == user_id
    assert account.enabled is True
    assert bot.sent[-1] == FakeSend(chat_id="42", text=BOUND_TEXT)


def test_bind_code_command_binds_sender_to_code_owner_without_allowlist() -> None:
    user_id = _reset_telegram_bridge_data()
    bot = FakeBotClient()
    with session_local() as session:
        TelegramBindCodeRepository(session).create(
            user_id=user_id,
            code="ABCD2345",
            expires_at=datetime.utcnow() + timedelta(minutes=10),
        )
        service = TelegramBridgeService(
            db=session,
            bot_client=bot,
            allowed_values={"some-other-chat"},
            default_user_email=None,
        )

        result = asyncio.run(service.handle_update(_telegram_update(text_value="/bind abcd2345", username="intruder")))
        account = TelegramAccountRepository(session).get_by_chat_id(chat_id="42")
        used_at = session.execute(text("SELECT used_at FROM telegram_bind_codes LIMIT 1")).scalar_one()

    assert result.processed is True
    assert result.message == "bound"
    assert result.user_id == user_id
    assert account is not None
    assert str(account.user_id) == user_id
    assert used_at is not None
    assert bot.sent[-1] == FakeSend(chat_id="42", text=BOUND_TEXT)


def test_bind_code_command_rejects_invalid_code_without_default_binding() -> None:
    user_id = _reset_telegram_bridge_data()
    bot = FakeBotClient()
    with session_local() as session:
        service = TelegramBridgeService(
            db=session,
            bot_client=bot,
            allowed_values={"42"},
            default_user_email="telegram@example.com",
        )

        result = asyncio.run(service.handle_update(_telegram_update(text_value="/bind WRONG999")))
        account = TelegramAccountRepository(session).get_by_chat_id(chat_id="42")

    assert result.processed is False
    assert result.message == "invalid_bind_code"
    assert account is None
    assert bot.sent
    assert bot.sent[-1].chat_id == "42"
    assert "绑定码" in bot.sent[-1].text


def test_unbound_regular_message_does_not_default_bind_admin(monkeypatch) -> None:
    _reset_telegram_bridge_data()
    bot = FakeBotClient()

    async def fake_run_chat(self, *, user_id: str, message: str, session_id: str | None = None, telegram_chat_id: str | None = None) -> TelegramChatRunResult:
        return TelegramChatRunResult(reply="unexpected chat reply", session_id=session_id)

    monkeypatch.setattr(TelegramBridgeService, "_run_chat", fake_run_chat)
    with session_local() as session:
        service = TelegramBridgeService(
            db=session,
            bot_client=bot,
            allowed_values={"42"},
            default_user_email="telegram@example.com",
        )

        result = asyncio.run(service.handle_update(_telegram_update(text_value="直接提问")))
        account = TelegramAccountRepository(session).get_by_chat_id(chat_id="42")

    assert result.processed is False
    assert result.message == "not_bound"
    assert account is None
    assert "绑定码" in bot.sent[-1].text


def test_handle_update_replies_to_bound_chat_without_managing_event_loop(monkeypatch) -> None:
    user_id = _reset_telegram_bridge_data()
    bot = FakeBotClient()

    async def fake_run_chat(self, *, user_id: str, message: str, session_id: str | None = None, telegram_chat_id: str | None = None) -> TelegramChatRunResult:
        assert session_id is None
        assert message == "帮我看今天计划"
        return TelegramChatRunResult(reply=f"reply for {user_id}", session_id=None)

    monkeypatch.setattr(TelegramBridgeService, "_run_chat", fake_run_chat)
    with session_local() as session:
        TelegramAccountRepository(session).upsert(user_id=user_id, chat_id="42", username="alice", first_name="Alice")
        service = TelegramBridgeService(
            db=session,
            bot_client=bot,
            allowed_values={"42"},
            default_user_email="telegram@example.com",
        )

        result = asyncio.run(service.handle_update(_telegram_update(text_value="帮我看今天计划")))

    assert result.processed is True
    assert result.message == "chat_replied"
    assert bot.sent[-1] == FakeSend(chat_id="42", text=f"reply for {user_id}")


def test_telegram_dream_command_uses_memory_command_handler(monkeypatch, tmp_path) -> None:
    bot = FakeBotClient()
    monkeypatch.setattr(settings, "ai_assistant_memory_dir", str(tmp_path))

    async def fail_run_chat(self, *, user_id: str, message: str, session_id: str | None = None, telegram_chat_id: str | None = None) -> TelegramChatRunResult:
        raise AssertionError("dream commands must not enter ordinary chat")

    monkeypatch.setattr(TelegramBridgeService, "_run_chat", fail_run_chat)
    service = TelegramBridgeService(
        db=None,
        bot_client=bot,
        allowed_values={"42"},
        default_user_email="telegram@example.com",
    )

    result = service._handle_memory_command(user_id="user-1", chat_id="42", text="/dream")

    assert result.processed is True
    assert result.message == "dream"
    assert "Dream" in bot.sent[-1].text


def test_handle_update_reuses_bound_telegram_chat_session(monkeypatch) -> None:
    user_id = _reset_telegram_bridge_data()
    bot = FakeBotClient()
    seen_session_ids: list[str | None] = []

    async def fake_run_chat(self, *, user_id: str, message: str, session_id: str | None = None, telegram_chat_id: str | None = None) -> TelegramChatRunResult:
        seen_session_ids.append(session_id)
        return TelegramChatRunResult(reply=f"reply: {message}", session_id=session_id or created_session_id)

    monkeypatch.setattr(TelegramBridgeService, "_run_chat", fake_run_chat)
    created_session_id = ""
    with session_local() as session:
        sticky_session = ChatSessionRepository(session).create(
            user_id=user_id,
            messages=[],
            agent_states={},
            last_agent="chat_assistant",
            token_count=0,
        )
        session_id = str(sticky_session.id)
        created_session_id = session_id
        account = TelegramAccountRepository(session).upsert(user_id=user_id, chat_id="42", username="alice", first_name="Alice")
        assert getattr(account, "chat_session_id", None) is None
        service = TelegramBridgeService(
            db=session,
            bot_client=bot,
            allowed_values={"42"},
            default_user_email="telegram@example.com",
        )

        first = asyncio.run(service.handle_update(_telegram_update(text_value="first")))
        account = TelegramAccountRepository(session).get_by_chat_id(chat_id="42")
        assert account is not None
        assert str(account.chat_session_id) == session_id

        second = asyncio.run(service.handle_update(_telegram_update(text_value="second")))

    assert first.message == "chat_replied"
    assert second.message == "chat_replied"
    assert seen_session_ids == [None, session_id]


def test_new_command_creates_fresh_telegram_chat_session(monkeypatch) -> None:
    user_id = _reset_telegram_bridge_data()
    bot = FakeBotClient()

    async def fake_run_chat(self, *, user_id: str, message: str, session_id: str | None = None, telegram_chat_id: str | None = None) -> TelegramChatRunResult:
        return TelegramChatRunResult(reply="unexpected chat reply", session_id=session_id)

    monkeypatch.setattr(TelegramBridgeService, "_run_chat", fake_run_chat)
    with session_local() as session:
        old_session = ChatSessionRepository(session).create(
            user_id=user_id,
            messages=[{"role": "user", "content": "old"}],
            agent_states={},
            last_agent="chat_assistant",
            token_count=3,
        )
        old_session_id = str(old_session.id)
        account = TelegramAccountRepository(session).upsert(user_id=user_id, chat_id="42", username="alice", first_name="Alice")
        account.chat_session_id = old_session_id
        session.add(account)
        session.commit()

        service = TelegramBridgeService(
            db=session,
            bot_client=bot,
            allowed_values={"42"},
            default_user_email="telegram@example.com",
        )

        result = asyncio.run(service.handle_update(_telegram_update(text_value="/new")))
        account = TelegramAccountRepository(session).get_by_chat_id(chat_id="42")
        assert account is not None
        new_session_id = str(account.chat_session_id)
        new_session = ChatSessionRepository(session).get_by_id(session_id=new_session_id, user_id=user_id)

    assert result.processed is True
    assert result.message == "new_session"
    assert new_session_id != old_session_id
    assert new_session is not None
    assert list(new_session.messages or []) == []
    assert "新开" in bot.sent[-1].text


def test_new_command_with_message_starts_fresh_session_then_runs_chat(monkeypatch) -> None:
    user_id = _reset_telegram_bridge_data()
    bot = FakeBotClient()
    seen_messages: list[str] = []
    seen_session_ids: list[str | None] = []

    async def fake_run_chat(self, *, user_id: str, message: str, session_id: str | None = None, telegram_chat_id: str | None = None) -> TelegramChatRunResult:
        seen_messages.append(message)
        seen_session_ids.append(session_id)
        return TelegramChatRunResult(reply="new session reply", session_id=session_id)

    monkeypatch.setattr(TelegramBridgeService, "_run_chat", fake_run_chat)
    with session_local() as session:
        old_session = ChatSessionRepository(session).create(
            user_id=user_id,
            messages=[{"role": "user", "content": "old"}],
            agent_states={},
            last_agent="chat_assistant",
            token_count=3,
        )
        old_session_id = str(old_session.id)
        account = TelegramAccountRepository(session).upsert(user_id=user_id, chat_id="42", username="alice", first_name="Alice")
        account.chat_session_id = old_session_id
        session.add(account)
        session.commit()

        service = TelegramBridgeService(
            db=session,
            bot_client=bot,
            allowed_values={"42"},
            default_user_email="telegram@example.com",
        )

        result = asyncio.run(service.handle_update(_telegram_update(text_value="/new 帮我重新规划求职")))
        account = TelegramAccountRepository(session).get_by_chat_id(chat_id="42")
        assert account is not None
        new_session_id = str(account.chat_session_id)

    assert result.processed is True
    assert result.message == "chat_replied"
    assert new_session_id != old_session_id
    assert seen_messages == ["帮我重新规划求职"]
    assert seen_session_ids == [new_session_id]
    assert bot.sent[-1] == FakeSend(chat_id="42", text="new session reply")


def test_current_command_reports_active_telegram_session(monkeypatch) -> None:
    user_id = _reset_telegram_bridge_data()
    bot = FakeBotClient()

    async def fake_run_chat(self, *, user_id: str, message: str, session_id: str | None = None, telegram_chat_id: str | None = None) -> TelegramChatRunResult:
        return TelegramChatRunResult(reply="unexpected chat reply", session_id=session_id)

    monkeypatch.setattr(TelegramBridgeService, "_run_chat", fake_run_chat)
    with session_local() as session:
        current_session = ChatSessionRepository(session).create(
            user_id=user_id,
            messages=[
                {"role": "user", "content": "帮我看简历"},
                {"role": "assistant", "content": "可以"},
            ],
            agent_states={},
            last_agent="chat_assistant",
            token_count=8,
        )
        account = TelegramAccountRepository(session).upsert(user_id=user_id, chat_id="42", username="alice", first_name="Alice")
        account.chat_session_id = str(current_session.id)
        session.add(account)
        session.commit()

        service = TelegramBridgeService(
            db=session,
            bot_client=bot,
            allowed_values={"42"},
            default_user_email="telegram@example.com",
        )

        result = asyncio.run(service.handle_update(_telegram_update(text_value="/current")))

    assert result.processed is True
    assert result.message == "current_session"
    assert str(current_session.id)[:8] in bot.sent[-1].text
    assert "帮我看简历" in bot.sent[-1].text
    assert "1 turns" in bot.sent[-1].text


def test_sessions_command_lists_recent_chat_sessions() -> None:
    user_id = _reset_telegram_bridge_data()
    bot = FakeBotClient()
    with session_local() as session:
        first = ChatSessionRepository(session).create(
            user_id=user_id,
            messages=[{"role": "user", "content": "第一轮"}],
            agent_states={},
            last_agent="chat_assistant",
            token_count=3,
        )
        second = ChatSessionRepository(session).create(
            user_id=user_id,
            messages=[{"role": "user", "content": "第二轮"}],
            agent_states={},
            last_agent="chat_assistant",
            token_count=3,
        )
        account = TelegramAccountRepository(session).upsert(user_id=user_id, chat_id="42", username="alice", first_name="Alice")
        account.chat_session_id = str(second.id)
        session.add(account)
        session.commit()

        service = TelegramBridgeService(
            db=session,
            bot_client=bot,
            allowed_values={"42"},
            default_user_email="telegram@example.com",
        )

        result = asyncio.run(service.handle_update(_telegram_update(text_value="/sessions")))

    assert result.processed is True
    assert result.message == "sessions"
    assert str(second.id)[:8] in bot.sent[-1].text
    assert str(first.id)[:8] in bot.sent[-1].text
    assert "第二轮" in bot.sent[-1].text
    assert "第一轮" in bot.sent[-1].text


def test_use_command_switches_to_owned_chat_session() -> None:
    user_id = _reset_telegram_bridge_data()
    bot = FakeBotClient()
    with session_local() as session:
        target = ChatSessionRepository(session).create(
            user_id=user_id,
            messages=[{"role": "user", "content": "目标会话"}],
            agent_states={},
            last_agent="chat_assistant",
            token_count=4,
        )
        other = ChatSessionRepository(session).create(
            user_id=user_id,
            messages=[{"role": "user", "content": "其他会话"}],
            agent_states={},
            last_agent="chat_assistant",
            token_count=4,
        )
        account = TelegramAccountRepository(session).upsert(user_id=user_id, chat_id="42", username="alice", first_name="Alice")
        account.chat_session_id = str(other.id)
        session.add(account)
        session.commit()

        service = TelegramBridgeService(
            db=session,
            bot_client=bot,
            allowed_values={"42"},
            default_user_email="telegram@example.com",
        )

        result = asyncio.run(service.handle_update(_telegram_update(text_value=f"/use {str(target.id)[:8]}")))
        account = TelegramAccountRepository(session).get_by_chat_id(chat_id="42")

    assert result.processed is True
    assert result.message == "session_switched"
    assert account is not None
    assert str(account.chat_session_id) == str(target.id)
    assert "目标会话" in bot.sent[-1].text


def test_handle_update_stop_disables_bound_account() -> None:
    user_id = _reset_telegram_bridge_data()
    bot = FakeBotClient()
    with session_local() as session:
        TelegramAccountRepository(session).upsert(user_id=user_id, chat_id="42", username="alice", first_name="Alice")
        service = TelegramBridgeService(
            db=session,
            bot_client=bot,
            allowed_values={"42"},
            default_user_email="telegram@example.com",
        )

        result = asyncio.run(service.handle_update(_telegram_update(text_value="/stop")))
        account = TelegramAccountRepository(session).get_by_chat_id(chat_id="42")

    assert result.processed is True
    assert result.message == "stopped"
    assert account is not None
    assert account.enabled is False
    assert bot.sent[-1] == FakeSend(chat_id="42", text=STOPPED_TEXT)


def test_telegram_schedule_message_creates_visible_telegram_delivery_task() -> None:
    user_id = _reset_telegram_bridge_data()
    bot = FakeBotClient()
    with session_local() as session:
        TelegramAccountRepository(session).upsert(user_id=user_id, chat_id="42", username="alice", first_name="Alice")
        service = TelegramBridgeService(
            db=session,
            bot_client=bot,
            allowed_values={"42"},
            default_user_email="telegram@example.com",
        )

        result = asyncio.run(service.handle_update(_telegram_update(text_value="3分钟后给我发送java的三条岗位信息")))
        row = session.execute(
            text(
                """
                SELECT source_channel, delivery_channel, telegram_chat_id
                FROM assistant_scheduled_tasks
                ORDER BY created_at DESC
                LIMIT 1
                """
            )
        ).mappings().one()

    assert result.processed is True
    assert result.message == "chat_replied"
    assert row["source_channel"] == "telegram"
    assert row["delivery_channel"] == "telegram"
    assert row["telegram_chat_id"] == "42"
    assert "会直接发到当前 Telegram 聊天" in bot.sent[-1].text
