"""Repository for isolated long-term memories of each assistant."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session


class AssistantMemoryRepository:
    def __init__(self, db: Session, *, compaction_threshold: int = 20, compaction_batch_size: int = 8):
        self.db = db
        self.compaction_threshold = compaction_threshold
        self.compaction_batch_size = max(1, compaction_batch_size)

    def upsert(
        self,
        *,
        user_id: str,
        assistant_type: str,
        scope_type: str,
        key: str,
        memory_kind: str,
        value: dict[str, Any],
        summary: str | None,
        confidence: float = 0.5,
        source: str | None = None,
        source_ref: dict[str, Any] | None = None,
        scope_id: str | None = None,
        expires_at: datetime | None = None,
    ) -> dict[str, Any]:
        existing_id = self.db.execute(
            text(
                """
                SELECT id
                FROM assistant_memories
                WHERE user_id = :user_id
                  AND assistant_type = :assistant_type
                  AND scope_type = :scope_type
                  AND ((scope_id IS NULL AND CAST(:scope_id AS uuid) IS NULL) OR scope_id = CAST(:scope_id AS uuid))
                  AND key = :key
                LIMIT 1
                """
            ),
            {
                "user_id": user_id,
                "assistant_type": assistant_type,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "key": key,
            },
        ).scalar_one_or_none()

        params = {
            "user_id": user_id,
            "assistant_type": assistant_type,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "key": key,
            "memory_kind": memory_kind,
            "value": json.dumps(value, ensure_ascii=False),
            "summary": summary,
            "confidence": confidence,
            "source": source,
            "source_ref": json.dumps(source_ref or {}, ensure_ascii=False),
            "expires_at": expires_at,
        }
        if existing_id is None:
            row = self.db.execute(
                text(
                    """
                    INSERT INTO assistant_memories (
                        user_id, assistant_type, scope_type, scope_id, memory_kind, key, value,
                        summary, confidence, source, source_ref, expires_at, updated_at, deleted_at
                    )
                    VALUES (
                        :user_id, :assistant_type, :scope_type, CAST(:scope_id AS uuid), :memory_kind, :key,
                        CAST(:value AS jsonb), :summary, :confidence, :source, CAST(:source_ref AS jsonb),
                        :expires_at, now(), NULL
                    )
                    RETURNING id, assistant_type, scope_type, scope_id, memory_kind, key, value, summary, confidence, source, source_ref
                    """
                ),
                params,
            ).mappings().one()
        else:
            row = self.db.execute(
                text(
                    """
                    UPDATE assistant_memories
                    SET memory_kind = :memory_kind,
                        value = CAST(:value AS jsonb),
                        summary = :summary,
                        confidence = :confidence,
                        source = :source,
                        source_ref = CAST(:source_ref AS jsonb),
                        expires_at = :expires_at,
                        updated_at = now(),
                        deleted_at = NULL
                    WHERE id = :id
                    RETURNING id, assistant_type, scope_type, scope_id, memory_kind, key, value, summary, confidence, source, source_ref
                    """
                ),
                {**params, "id": str(existing_id)},
            ).mappings().one()
        memory = self._row_to_dict(row)
        self.db.commit()
        memory["compaction"] = self._compact_if_needed(
            user_id=user_id,
            assistant_type=assistant_type,
            scope_type=scope_type,
            scope_id=scope_id,
        )
        return memory

    def list_active(
        self,
        *,
        user_id: str,
        assistant_type: str,
        scope_type: str | None = None,
        scope_id: str | None = None,
        limit: int = 20,
        include_pending: bool = False,
    ) -> list[dict[str, Any]]:
        filters = [
            "user_id = :user_id",
            "assistant_type = :assistant_type",
            "deleted_at IS NULL",
            "(expires_at IS NULL OR expires_at > now())",
        ]
        if not include_pending:
            filters.append("memory_kind <> 'pending'")
        params: dict[str, Any] = {"user_id": user_id, "assistant_type": assistant_type, "limit": limit}
        if scope_type is not None:
            filters.append("scope_type = :scope_type")
            params["scope_type"] = scope_type
        if scope_id is not None:
            filters.append("scope_id = CAST(:scope_id AS uuid)")
            params["scope_id"] = scope_id

        rows = self.db.execute(
            text(
                f"""
                SELECT id, assistant_type, scope_type, scope_id, memory_kind, key, value, summary, confidence, source, source_ref, updated_at
                FROM assistant_memories
                WHERE {' AND '.join(filters)}
                ORDER BY updated_at DESC
                LIMIT :limit
                """
            ),
            params,
        ).mappings()
        return [self._row_to_dict(row) for row in rows]

    def stage_pending(
        self,
        *,
        user_id: str,
        assistant_type: str,
        scope_type: str,
        key: str,
        memory_kind: str,
        value: dict[str, Any],
        summary: str | None,
        confidence: float = 0.5,
        source: str | None = None,
        source_ref: dict[str, Any] | None = None,
        scope_id: str | None = None,
        expires_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Stage a memory candidate that remains hidden until confirmation."""
        pending_key = f"pending::{key}::{uuid4()}"
        pending_value = {
            "candidate_key": key,
            "candidate_memory_kind": memory_kind,
            "candidate_value": value,
        }
        row = self.db.execute(
            text(
                """
                INSERT INTO assistant_memories (
                    user_id, assistant_type, scope_type, scope_id, memory_kind, key, value,
                    summary, confidence, source, source_ref, expires_at, updated_at, deleted_at
                )
                VALUES (
                    :user_id, :assistant_type, :scope_type, CAST(:scope_id AS uuid),
                    'pending', :key, CAST(:value AS jsonb), :summary, :confidence,
                    :source, CAST(:source_ref AS jsonb), :expires_at, now(), NULL
                )
                RETURNING id, assistant_type, scope_type, scope_id, memory_kind, key, value, summary, confidence, source, source_ref
                """
            ),
            {
                "user_id": user_id,
                "assistant_type": assistant_type,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "key": pending_key,
                "value": json.dumps(pending_value, ensure_ascii=False),
                "summary": summary,
                "confidence": confidence,
                "source": source,
                "source_ref": json.dumps(source_ref or {}, ensure_ascii=False),
                "expires_at": expires_at,
            },
        ).mappings().one()
        self.db.commit()
        return self._row_to_dict(row)

    def confirm_pending(
        self,
        *,
        user_id: str,
        assistant_type: str,
        pending_id: str,
    ) -> dict[str, Any]:
        """Promote a pending memory into durable memory and soft-delete the candidate."""
        row = self.db.execute(
            text(
                """
                SELECT id, scope_type, scope_id, value, summary, confidence, source, source_ref
                FROM assistant_memories
                WHERE id = CAST(:pending_id AS uuid)
                  AND user_id = :user_id
                  AND assistant_type = :assistant_type
                  AND memory_kind = 'pending'
                  AND deleted_at IS NULL
                LIMIT 1
                """
            ),
            {"pending_id": pending_id, "user_id": user_id, "assistant_type": assistant_type},
        ).mappings().one_or_none()
        if row is None:
            raise ValueError("pending memory not found")

        pending_value = row.get("value") if isinstance(row.get("value"), dict) else {}
        confirmed = self.upsert(
            user_id=user_id,
            assistant_type=assistant_type,
            scope_type=row["scope_type"],
            scope_id=str(row["scope_id"]) if row["scope_id"] else None,
            key=str(pending_value.get("candidate_key") or "memory"),
            memory_kind=str(pending_value.get("candidate_memory_kind") or "profile_fact"),
            value=dict(pending_value.get("candidate_value") or {}),
            summary=row.get("summary"),
            confidence=float(row.get("confidence") or 0.5),
            source=row.get("source"),
            source_ref=dict(row.get("source_ref") or {}),
        )
        self.db.execute(
            text(
                """
                UPDATE assistant_memories
                SET deleted_at = now(), updated_at = now()
                WHERE id = CAST(:pending_id AS uuid)
                """
            ),
            {"pending_id": pending_id},
        )
        self.db.commit()
        confirmed["pending_id"] = pending_id
        return confirmed

    def soft_delete(
        self,
        *,
        user_id: str,
        assistant_type: str,
        key: str,
        deleted_at: datetime | None = None,
        scope_type: str | None = None,
        scope_id: str | None = None,
    ) -> int:
        filters = ["user_id = :user_id", "assistant_type = :assistant_type", "key = :key", "deleted_at IS NULL"]
        params: dict[str, Any] = {
            "user_id": user_id,
            "assistant_type": assistant_type,
            "key": key,
            "deleted_at": deleted_at or datetime.utcnow(),
        }
        if scope_type is not None:
            filters.append("scope_type = :scope_type")
            params["scope_type"] = scope_type
        if scope_id is not None:
            filters.append("scope_id = CAST(:scope_id AS uuid)")
            params["scope_id"] = scope_id
        result = self.db.execute(
            text(
                f"""
                UPDATE assistant_memories
                SET deleted_at = :deleted_at, updated_at = now()
                WHERE {' AND '.join(filters)}
                """
            ),
            params,
        )
        self.db.commit()
        return int(result.rowcount or 0)

    def _compact_if_needed(
        self,
        *,
        user_id: str,
        assistant_type: str,
        scope_type: str,
        scope_id: str | None,
    ) -> dict[str, Any]:
        if self.compaction_threshold <= 0:
            return {"compacted": False, "count": 0, "reason": "disabled"}

        rows = list(
            self.db.execute(
                text(
                    """
                    SELECT id, key, memory_kind, value, summary, confidence, source, source_ref, updated_at
                    FROM assistant_memories
                    WHERE user_id = :user_id
                      AND assistant_type = :assistant_type
                      AND scope_type = :scope_type
                      AND ((scope_id IS NULL AND CAST(:scope_id AS uuid) IS NULL) OR scope_id = CAST(:scope_id AS uuid))
                      AND deleted_at IS NULL
                      AND (expires_at IS NULL OR expires_at > now())
                      AND memory_kind NOT IN ('compressed_summary', 'pending')
                    ORDER BY updated_at ASC, id ASC
                    """
                ),
                {
                    "user_id": user_id,
                    "assistant_type": assistant_type,
                    "scope_type": scope_type,
                    "scope_id": scope_id,
                },
            ).mappings()
        )
        if len(rows) <= self.compaction_threshold:
            return {"compacted": False, "count": 0, "ordinary_active_count": len(rows)}

        selected = rows[: min(self.compaction_batch_size, len(rows))]
        compressed_key = "__compressed_summary__"
        existing = self.db.execute(
            text(
                """
                SELECT id, value
                FROM assistant_memories
                WHERE user_id = :user_id
                  AND assistant_type = :assistant_type
                  AND scope_type = :scope_type
                  AND ((scope_id IS NULL AND CAST(:scope_id AS uuid) IS NULL) OR scope_id = CAST(:scope_id AS uuid))
                  AND key = :key
                  AND deleted_at IS NULL
                LIMIT 1
                """
            ),
            {
                "user_id": user_id,
                "assistant_type": assistant_type,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "key": compressed_key,
            },
        ).mappings().one_or_none()

        existing_value = existing["value"] if existing and isinstance(existing["value"], dict) else {}
        previous_items = list(existing_value.get("items") or [])
        new_items = [
            {
                "key": row.get("key"),
                "memory_kind": row.get("memory_kind"),
                "summary": row.get("summary"),
                "source": row.get("source"),
                "source_ref": row.get("source_ref") if isinstance(row.get("source_ref"), dict) else {},
                "confidence": float(row.get("confidence") or 0.0),
                "updated_at": row.get("updated_at").isoformat() if row.get("updated_at") else None,
            }
            for row in selected
        ]
        item_count = int(existing_value.get("item_count") or len(previous_items)) + len(new_items)
        retained_items = (previous_items + new_items)[-50:]
        summary_text = self._compact_summary_text(assistant_type=assistant_type, items=retained_items, item_count=item_count)
        compressed_value = {
            "item_count": item_count,
            "items": retained_items,
            "summary_version": 1,
        }

        if existing is None:
            self.db.execute(
                text(
                    """
                    INSERT INTO assistant_memories (
                        user_id, assistant_type, scope_type, scope_id, memory_kind, key, value,
                        summary, confidence, source, source_ref, updated_at, deleted_at
                    )
                    VALUES (
                        :user_id, :assistant_type, :scope_type, CAST(:scope_id AS uuid),
                        'compressed_summary', :key, CAST(:value AS jsonb),
                        :summary, 0.7, 'memory_compactor', CAST(:source_ref AS jsonb), now(), NULL
                    )
                    """
                ),
                {
                    "user_id": user_id,
                    "assistant_type": assistant_type,
                    "scope_type": scope_type,
                    "scope_id": scope_id,
                    "key": compressed_key,
                    "value": json.dumps(compressed_value, ensure_ascii=False),
                    "summary": summary_text,
                    "source_ref": json.dumps({"kind": "memory_compaction", "item_count": item_count}, ensure_ascii=False),
                },
            )
        else:
            self.db.execute(
                text(
                    """
                    UPDATE assistant_memories
                    SET value = CAST(:value AS jsonb),
                        summary = :summary,
                        confidence = 0.7,
                        source = 'memory_compactor',
                        source_ref = CAST(:source_ref AS jsonb),
                        updated_at = now(),
                        deleted_at = NULL
                    WHERE id = :id
                    """
                ),
                {
                    "id": str(existing["id"]),
                    "value": json.dumps(compressed_value, ensure_ascii=False),
                    "summary": summary_text,
                    "source_ref": json.dumps({"kind": "memory_compaction", "item_count": item_count}, ensure_ascii=False),
                },
            )

        for row in selected:
            self.db.execute(
                text(
                    """
                    UPDATE assistant_memories
                    SET deleted_at = now(), updated_at = now()
                    WHERE id = :id
                    """
                ),
                {"id": str(row["id"])},
            )
        self.db.commit()
        return {
            "compacted": True,
            "count": len(selected),
            "summary_key": compressed_key,
            "ordinary_active_count": len(rows) - len(selected),
        }

    @staticmethod
    def _compact_summary_text(*, assistant_type: str, items: list[dict[str, Any]], item_count: int) -> str:
        summaries = [str(item.get("summary") or item.get("key") or "").strip() for item in items if item.get("summary") or item.get("key")]
        preview = "；".join(summaries[-5:])
        return f"{assistant_type} compressed {item_count} old memories: {preview}"

    @staticmethod
    def _row_to_dict(row) -> dict[str, Any]:
        value = row.get("value")
        source_ref = row.get("source_ref")
        return {
            "id": str(row.get("id")),
            "assistant_type": row.get("assistant_type"),
            "scope_type": row.get("scope_type"),
            "scope_id": str(row.get("scope_id")) if row.get("scope_id") else None,
            "memory_kind": row.get("memory_kind"),
            "key": row.get("key"),
            "value": value if isinstance(value, dict) else {},
            "summary": row.get("summary"),
            "confidence": float(row.get("confidence") or 0.0),
            "source": row.get("source"),
            "source_ref": source_ref if isinstance(source_ref, dict) else {},
        }
