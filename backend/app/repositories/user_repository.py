from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email, User.deleted_at.is_(None))
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_id(self, user_id: str) -> User | None:
        stmt = select(User).where(User.id == user_id, User.deleted_at.is_(None))
        return self.db.execute(stmt).scalar_one_or_none()

    def create(self, *, email: str, password_hash: str, name: str, quota_reset_at: datetime) -> User:
        user = User(
            email=email,
            password_hash=password_hash,
            name=name,
            quota_reset_at=quota_reset_at,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user
