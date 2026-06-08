from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import jwt

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.settings import settings
from app.repositories.user_repository import UserRepository
from app.scripts.seed_default_user import DEFAULT_ADMIN_EMAIL, ensure_default_admin_user, normalize_login_identifier


@dataclass
class AuthServiceError(Exception):
    status_code: int
    code: int
    message: str


class AuthService:
    def __init__(self, user_repository: UserRepository):
        self.user_repository = user_repository

    @staticmethod
    def _next_quota_reset_at() -> datetime:
        now = datetime.now(UTC)
        year = now.year + (1 if now.month == 12 else 0)
        month = 1 if now.month == 12 else now.month + 1
        return datetime(year=year, month=month, day=1)

    def register(self, *, email: str, password: str, name: str) -> dict:
        normalized_email = email.strip().lower()
        existing_user = self.user_repository.get_by_email(normalized_email)
        if existing_user is not None:
            raise AuthServiceError(status_code=409, code=1001, message="Email already registered")

        user = self.user_repository.create(
            email=normalized_email,
            password_hash=hash_password(password),
            name=name,
            quota_reset_at=self._next_quota_reset_at(),
        )
        user_id = str(user.id)
        return {
            "user_id": user_id,
            "access_token": create_access_token(user_id),
            "refresh_token": create_refresh_token(user_id),
        }

    def login(self, *, email: str, password: str) -> dict:
        normalized_email = normalize_login_identifier(email)
        if normalized_email == DEFAULT_ADMIN_EMAIL:
            ensure_default_admin_user(self.user_repository.db)

        user = self.user_repository.get_by_email(normalized_email)
        if user is None or not verify_password(password, user.password_hash):
            raise AuthServiceError(status_code=401, code=1002, message="Invalid email or password")

        user_id = str(user.id)
        return {
            "access_token": create_access_token(user_id),
            "expires_in": settings.access_token_expire_seconds,
            "refresh_token": create_refresh_token(user_id),
        }

    def refresh_access_token(self, *, refresh_token: str) -> dict:
        try:
            payload = decode_token(refresh_token, expected_type="refresh")
        except (jwt.PyJWTError, ValueError):
            raise AuthServiceError(status_code=401, code=1003, message="Invalid refresh token")

        user_id = str(payload["sub"])
        return {
            "access_token": create_access_token(user_id),
            "expires_in": settings.access_token_expire_seconds,
        }
