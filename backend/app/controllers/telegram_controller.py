from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.core.settings import settings
from app.repositories.notification_repository import (
    TelegramAccountRepository,
    TelegramBindCodeRepository,
    generate_telegram_bind_code,
)

router = APIRouter(prefix="/api/v1/telegram", tags=["telegram"])


def _mask_chat_id(chat_id: str | None) -> str | None:
    if not chat_id:
        return None
    value = str(chat_id)
    if len(value) <= 4:
        return "***"
    return f"{value[:3]}***{value[-2:]}"


@router.get("/status")
def get_telegram_status(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    account = TelegramAccountRepository(db).get_by_user_id(user_id=user_id)
    if account is None:
        return {
            "code": 0,
            "data": {
                "bound": False,
                "enabled": False,
                "username": None,
                "first_name": None,
                "chat_id_masked": None,
                "last_seen_at": None,
                "chat_session_id": None,
            },
        }
    return {
        "code": 0,
        "data": {
            "bound": True,
            "enabled": bool(account.enabled),
            "username": account.username,
            "first_name": account.first_name,
            "chat_id_masked": _mask_chat_id(account.chat_id),
            "last_seen_at": account.last_seen_at.isoformat() if account.last_seen_at else None,
            "chat_session_id": str(account.chat_session_id) if account.chat_session_id else None,
        },
    }


@router.post("/bind-code")
def create_telegram_bind_code(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    code = generate_telegram_bind_code()
    expires_at = datetime.utcnow() + timedelta(minutes=settings.telegram_bind_code_ttl_minutes)
    TelegramBindCodeRepository(db).create(user_id=user_id, code=code, expires_at=expires_at)
    return {
        "code": 0,
        "data": {
            "code": code,
            "command": f"/bind {code}",
            "expires_at": expires_at.isoformat(),
            "ttl_minutes": settings.telegram_bind_code_ttl_minutes,
        },
    }
