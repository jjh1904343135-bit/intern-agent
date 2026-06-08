from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.orm import Session


class AgentMemoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def upsert(self, *, user_id: str, key: str, value: dict) -> None:
        self.db.execute(
            text(
                """
                INSERT INTO agent_memories (user_id, key, value, updated_at)
                VALUES (:user_id, :key, CAST(:value AS jsonb), now())
                ON CONFLICT (user_id, key)
                DO UPDATE SET value = EXCLUDED.value, updated_at = now()
                """
            ),
            {"user_id": user_id, "key": key, "value": json.dumps(value, ensure_ascii=False)},
        )
        self.db.commit()
