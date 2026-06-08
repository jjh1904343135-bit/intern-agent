from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.repositories.user_repository import UserRepository

DEFAULT_ADMIN_ALIAS = "admin"
DEFAULT_ADMIN_EMAIL = "admin@example.com"
DEFAULT_ADMIN_PASSWORD = "password"


def normalize_login_identifier(identifier: str) -> str:
    normalized = identifier.strip().lower()
    if normalized == DEFAULT_ADMIN_ALIAS:
        return DEFAULT_ADMIN_EMAIL
    return normalized


def _next_quota_reset_at() -> datetime:
    now = datetime.utcnow()
    year = now.year + (1 if now.month == 12 else 0)
    month = 1 if now.month == 12 else now.month + 1
    return datetime(year=year, month=month, day=1)


def ensure_default_admin_user(db: Session) -> None:

    repository = UserRepository(db)
    existing = repository.get_by_email(DEFAULT_ADMIN_EMAIL)
    password_hash = hash_password(DEFAULT_ADMIN_PASSWORD)
    if existing is None:
        repository.create(
            email=DEFAULT_ADMIN_EMAIL,
            password_hash=password_hash,
            name=DEFAULT_ADMIN_ALIAS,
            quota_reset_at=_next_quota_reset_at(),
        )
        return

    existing.password_hash = password_hash
    existing.name = DEFAULT_ADMIN_ALIAS
    existing.profile = {**(existing.profile or {}), "seeded_default": True}
    db.add(existing)
    db.commit()


def main() -> None:
    from app.core.database import session_local

    with session_local() as db:
        ensure_default_admin_user(db)


if __name__ == "__main__":
    main()
