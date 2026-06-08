from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, time, timedelta
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.notification import NotificationEvent, TelegramAccount, TelegramBindCode

TELEGRAM_BIND_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_telegram_bind_code(*, length: int = 8) -> str:
    return "".join(secrets.choice(TELEGRAM_BIND_CODE_ALPHABET) for _ in range(length))


def normalize_telegram_bind_code(code: str) -> str:
    return "".join(str(code or "").strip().upper().split())


def hash_telegram_bind_code(code: str) -> str:
    return hashlib.sha256(normalize_telegram_bind_code(code).encode("utf-8")).hexdigest()


class TelegramAccountRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_chat_id(self, *, chat_id: str) -> TelegramAccount | None:
        stmt: Select[tuple[TelegramAccount]] = select(TelegramAccount).where(TelegramAccount.chat_id == str(chat_id))
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_user_id(self, *, user_id: str) -> TelegramAccount | None:
        stmt: Select[tuple[TelegramAccount]] = (
            select(TelegramAccount)
            .where(TelegramAccount.user_id == str(user_id))
            .order_by(TelegramAccount.updated_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def upsert(self, *, user_id: str, chat_id: str, username: str | None, first_name: str | None) -> TelegramAccount:
        now = datetime.utcnow()
        account = self.get_by_chat_id(chat_id=chat_id)
        if account is None:
            account = TelegramAccount(user_id=user_id, chat_id=str(chat_id), username=username, first_name=first_name)
        elif str(account.user_id) != str(user_id):
            account.chat_session_id = None
        account.user_id = user_id
        account.username = username
        account.first_name = first_name
        account.enabled = True
        account.updated_at = now
        account.last_seen_at = now
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        return account

    def mark_seen(
        self,
        *,
        account: TelegramAccount,
        username: str | None,
        first_name: str | None,
        chat_session_id: str | None = None,
    ) -> TelegramAccount:
        account.username = username or account.username
        account.first_name = first_name or account.first_name
        if chat_session_id is not None:
            account.chat_session_id = chat_session_id
        account.last_seen_at = datetime.utcnow()
        account.updated_at = datetime.utcnow()
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        return account

    def disable(self, *, account: TelegramAccount) -> TelegramAccount:
        account.enabled = False
        account.updated_at = datetime.utcnow()
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        return account

    def list_enabled(self, *, limit: int = 50) -> list[TelegramAccount]:
        stmt: Select[tuple[TelegramAccount]] = (
            select(TelegramAccount)
            .where(TelegramAccount.enabled.is_(True))
            .order_by(TelegramAccount.updated_at.desc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars())


class TelegramBindCodeRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, *, user_id: str, code: str, expires_at: datetime) -> TelegramBindCode:
        bind_code = TelegramBindCode(
            user_id=user_id,
            code_hash=hash_telegram_bind_code(code),
            expires_at=expires_at,
        )
        self.db.add(bind_code)
        self.db.commit()
        self.db.refresh(bind_code)
        return bind_code

    def consume(self, *, code: str, now: datetime) -> TelegramBindCode | None:
        stmt: Select[tuple[TelegramBindCode]] = (
            select(TelegramBindCode)
            .where(
                TelegramBindCode.code_hash == hash_telegram_bind_code(code),
                TelegramBindCode.used_at.is_(None),
                TelegramBindCode.expires_at > now,
            )
            .limit(1)
        )
        bind_code = self.db.execute(stmt).scalar_one_or_none()
        if bind_code is None:
            return None
        bind_code.used_at = now
        self.db.add(bind_code)
        self.db.commit()
        self.db.refresh(bind_code)
        return bind_code


class NotificationEventRepository:
    def __init__(self, db: Session):
        self.db = db

    def count_sent_today(self, *, user_id: str, channel: str, now: datetime) -> int:
        start = datetime.combine(now.date(), time.min)
        stmt = (
            select(func.count())
            .select_from(NotificationEvent)
            .where(
                NotificationEvent.user_id == user_id,
                NotificationEvent.channel == channel,
                NotificationEvent.status == "sent",
                NotificationEvent.sent_at >= start,
            )
        )
        return int(self.db.execute(stmt).scalar_one())

    def last_sent_event(
        self,
        *,
        user_id: str,
        channel: str,
        event_type: str | None = None,
        event_key: str | None = None,
    ) -> NotificationEvent | None:
        stmt: Select[tuple[NotificationEvent]] = (
            select(NotificationEvent)
            .where(
                NotificationEvent.user_id == user_id,
                NotificationEvent.channel == channel,
                NotificationEvent.status == "sent",
            )
            .order_by(NotificationEvent.sent_at.desc())
            .limit(1)
        )
        if event_type is not None:
            stmt = stmt.where(NotificationEvent.event_type == event_type)
        if event_key is not None:
            stmt = stmt.where(NotificationEvent.event_key == event_key)
        return self.db.execute(stmt).scalar_one_or_none()

    def last_sent_at(
        self,
        *,
        user_id: str,
        channel: str,
        event_type: str | None = None,
        event_key: str | None = None,
    ) -> datetime | None:
        row = self.last_sent_event(user_id=user_id, channel=channel, event_type=event_type, event_key=event_key)
        return row.sent_at if row is not None else None

    def recent_sent(self, *, user_id: str, channel: str, limit: int = 5) -> list[dict[str, Any]]:
        stmt: Select[tuple[NotificationEvent]] = (
            select(NotificationEvent)
            .where(
                NotificationEvent.user_id == user_id,
                NotificationEvent.channel == channel,
                NotificationEvent.status == "sent",
            )
            .order_by(NotificationEvent.sent_at.desc())
            .limit(limit)
        )
        return [
            {
                "event_type": item.event_type,
                "event_key": item.event_key,
                "message": item.message,
                "sent_at": item.sent_at.isoformat() if item.sent_at else None,
            }
            for item in self.db.execute(stmt).scalars()
        ]

    def record_sent(self, *, candidate, channel: str, decision, now: datetime) -> NotificationEvent:
        decision_payload = dict(getattr(decision, "raw", {}) or {})
        cooldown_hours = getattr(decision, "cooldown_hours", None)
        if cooldown_hours is not None:
            decision_payload["cooldown_hours"] = int(cooldown_hours)
        return self._record(
            candidate=candidate,
            channel=channel,
            status="sent",
            reason=decision.reason,
            message=decision.message,
            decision=decision_payload,
            now=now,
            sent_at=now,
        )

    def should_record_skip(self, *, candidate, channel: str, reason: str, now: datetime, cooldown_minutes: int = 60) -> bool:
        cutoff = now - timedelta(minutes=max(1, cooldown_minutes))
        stmt: Select[tuple[NotificationEvent]] = (
            select(NotificationEvent)
            .where(
                NotificationEvent.user_id == candidate.user_id,
                NotificationEvent.channel == channel,
                NotificationEvent.event_key == candidate.event_key,
                NotificationEvent.status == "skipped",
                NotificationEvent.reason == reason,
                NotificationEvent.created_at >= cutoff,
            )
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none() is None

    def record_skip(self, *, candidate, channel: str, reason: str, now: datetime, decision: dict | None = None) -> NotificationEvent:
        return self._record(
            candidate=candidate,
            channel=channel,
            status="skipped",
            reason=reason,
            message=None,
            decision=decision or {},
            now=now,
            sent_at=None,
        )

    def record_failed(self, *, candidate, channel: str, reason: str, now: datetime, decision: dict | None = None) -> NotificationEvent:
        return self._record(
            candidate=candidate,
            channel=channel,
            status="failed",
            reason=reason,
            message=None,
            decision=decision or {},
            now=now,
            sent_at=None,
        )

    def _record(
        self,
        *,
        candidate,
        channel: str,
        status: str,
        reason: str | None,
        message: str | None,
        decision: dict,
        now: datetime,
        sent_at: datetime | None,
    ) -> NotificationEvent:
        event = NotificationEvent(
            user_id=candidate.user_id,
            channel=channel,
            event_key=candidate.event_key,
            event_type=candidate.event_type,
            subject_id=str(candidate.evidence.get("application_id") or candidate.evidence.get("resume_id") or ""),
            status=status,
            reason=_truncate_reason(reason),
            message=message,
            decision=decision,
            evidence=candidate.evidence,
            event_time=candidate.event_time,
            sent_at=sent_at,
            created_at=now,
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event


def _truncate_reason(reason: str | None) -> str | None:
    if reason is None:
        return None
    return str(reason)[:120]
