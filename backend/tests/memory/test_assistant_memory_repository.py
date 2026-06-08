from __future__ import annotations

from datetime import datetime

from sqlalchemy import text

from app.core.database import session_local
from app.repositories.assistant_memory_repository import AssistantMemoryRepository


def _reset_memory_data() -> None:
    with session_local() as session:
        session.execute(text("DELETE FROM assistant_memories"))
        session.execute(text("DELETE FROM chat_sessions"))
        session.execute(text("DELETE FROM interview_sessions"))
        session.execute(text("DELETE FROM applications"))
        session.execute(text("DELETE FROM resumes"))
        session.execute(text("DELETE FROM jobs"))
        session.execute(text("DELETE FROM users"))
        session.commit()


def _create_user() -> str:
    with session_local() as session:
        user_id = session.execute(
            text(
                """
                INSERT INTO users (email, password_hash, name, quota_reset_at, created_at)
                VALUES ('memory@example.com', 'hash', 'Memory User', now(), now())
                RETURNING id
                """
            )
        ).scalar_one()
        session.commit()
        return str(user_id)


def test_assistant_memories_are_isolated_by_assistant_type() -> None:
    _reset_memory_data()
    user_id = _create_user()

    with session_local() as session:
        repository = AssistantMemoryRepository(session)
        repository.upsert(
            user_id=user_id,
            assistant_type="ai_assistant",
            scope_type="global",
            key="target_role",
            memory_kind="preference",
            value={"role": "Java 后端"},
            summary="偏好 Java 后端岗位",
            confidence=0.9,
            source="chat",
        )
        repository.upsert(
            user_id=user_id,
            assistant_type="interview_assistant",
            scope_type="global",
            key="target_role",
            memory_kind="interview_pattern",
            value={"weakness": "回答缺少量化指标"},
            summary="面试回答缺少量化指标",
            confidence=0.8,
            source="interview",
        )

        ai_memories = repository.list_active(user_id=user_id, assistant_type="ai_assistant")
        interview_memories = repository.list_active(user_id=user_id, assistant_type="interview_assistant")

    assert [memory["summary"] for memory in ai_memories] == ["偏好 Java 后端岗位"]
    assert [memory["summary"] for memory in interview_memories] == ["面试回答缺少量化指标"]


def test_assistant_memory_upsert_updates_same_scope_without_cross_pollution() -> None:
    _reset_memory_data()
    user_id = _create_user()

    with session_local() as session:
        repository = AssistantMemoryRepository(session)
        repository.upsert(
            user_id=user_id,
            assistant_type="ai_assistant",
            scope_type="global",
            key="target_city",
            memory_kind="preference",
            value={"city": "北京"},
            summary="目标城市北京",
            confidence=0.6,
            source="chat",
        )
        repository.upsert(
            user_id=user_id,
            assistant_type="ai_assistant",
            scope_type="global",
            key="target_city",
            memory_kind="preference",
            value={"city": "上海"},
            summary="目标城市上海",
            confidence=0.7,
            source="chat",
        )

        memories = repository.list_active(user_id=user_id, assistant_type="ai_assistant")

    assert len(memories) == 1
    assert memories[0]["value"] == {"city": "上海"}
    assert memories[0]["summary"] == "目标城市上海"


def test_assistant_memory_soft_delete_does_not_affect_other_assistant() -> None:
    _reset_memory_data()
    user_id = _create_user()

    with session_local() as session:
        repository = AssistantMemoryRepository(session)
        repository.upsert(
            user_id=user_id,
            assistant_type="ai_assistant",
            scope_type="global",
            key="target_role",
            memory_kind="preference",
            value={"role": "产品经理"},
            summary="偏好产品经理",
            confidence=0.9,
            source="chat",
        )
        repository.upsert(
            user_id=user_id,
            assistant_type="interview_assistant",
            scope_type="global",
            key="target_role",
            memory_kind="interview_pattern",
            value={"role": "产品经理"},
            summary="产品岗面试表达偏泛",
            confidence=0.8,
            source="interview",
        )
        repository.soft_delete(user_id=user_id, assistant_type="ai_assistant", key="target_role", deleted_at=datetime.utcnow())

        ai_memories = repository.list_active(user_id=user_id, assistant_type="ai_assistant")
        interview_memories = repository.list_active(user_id=user_id, assistant_type="interview_assistant")

    assert ai_memories == []
    assert len(interview_memories) == 1
    assert interview_memories[0]["summary"] == "产品岗面试表达偏泛"


def test_assistant_memory_auto_compacts_old_items_without_cross_assistant_pollution() -> None:
    _reset_memory_data()
    user_id = _create_user()

    with session_local() as session:
        repository = AssistantMemoryRepository(session, compaction_threshold=3, compaction_batch_size=2)
        for index in range(3):
            repository.upsert(
                user_id=user_id,
                assistant_type="ai_assistant",
                scope_type="global",
                key=f"preference_{index}",
                memory_kind="preference",
                value={"index": index},
                summary=f"preference {index}",
                confidence=0.6,
                source="chat",
            )

        compacting_write = repository.upsert(
            user_id=user_id,
            assistant_type="ai_assistant",
            scope_type="global",
            key="preference_3",
            memory_kind="preference",
            value={"index": 3},
            summary="preference 3",
            confidence=0.6,
            source="chat",
        )
        repository.upsert(
            user_id=user_id,
            assistant_type="interview_assistant",
            scope_type="global",
            key="interview_marker",
            memory_kind="interview_pattern",
            value={"weakness": "too short"},
            summary="interview memory should stay separate",
            confidence=0.8,
            source="interview",
        )

        ai_memories = repository.list_active(user_id=user_id, assistant_type="ai_assistant", limit=20)
        interview_memories = repository.list_active(user_id=user_id, assistant_type="interview_assistant", limit=20)
        deleted_count = session.execute(
            text(
                """
                SELECT count(*)
                FROM assistant_memories
                WHERE user_id = :user_id
                  AND assistant_type = 'ai_assistant'
                  AND deleted_at IS NOT NULL
                """
            ),
            {"user_id": user_id},
        ).scalar_one()

    compressed = [memory for memory in ai_memories if memory["memory_kind"] == "compressed_summary"]
    ordinary = [memory for memory in ai_memories if memory["memory_kind"] != "compressed_summary"]
    assert compacting_write["compaction"]["compacted"] is True
    assert compacting_write["compaction"]["count"] == 2
    assert len(compressed) == 1
    assert len(ordinary) <= 3
    assert compressed[0]["value"]["item_count"] == 2
    assert compressed[0]["value"]["items"][0]["summary"] == "preference 0"
    assert deleted_count == 2
    assert [memory["key"] for memory in interview_memories] == ["interview_marker"]


def test_pending_memory_is_hidden_until_confirmed_and_keeps_source_ref() -> None:
    _reset_memory_data()
    user_id = _create_user()

    with session_local() as session:
        repository = AssistantMemoryRepository(session)
        pending = repository.stage_pending(
            user_id=user_id,
            assistant_type="ai_assistant",
            scope_type="global",
            key="target_role",
            memory_kind="preference",
            value={"role": "Java Backend Intern"},
            summary="prefers Java backend internships",
            confidence=0.82,
            source="chat_turn",
            source_ref={
                "kind": "chat_turn",
                "request_id": "req-1",
                "agent_run_id": "chat-1",
                "message_id": "user-1",
            },
        )

        active_before = repository.list_active(user_id=user_id, assistant_type="ai_assistant")
        confirmed = repository.confirm_pending(
            user_id=user_id,
            assistant_type="ai_assistant",
            pending_id=pending["id"],
        )
        active_after = repository.list_active(user_id=user_id, assistant_type="ai_assistant")
        pending_count = session.execute(
            text(
                """
                SELECT count(*)
                FROM assistant_memories
                WHERE user_id = :user_id
                  AND assistant_type = 'ai_assistant'
                  AND memory_kind = 'pending'
                  AND deleted_at IS NULL
                """
            ),
            {"user_id": user_id},
        ).scalar_one()

    assert pending["memory_kind"] == "pending"
    assert pending["source_ref"]["request_id"] == "req-1"
    assert active_before == []
    assert confirmed["key"] == "target_role"
    assert confirmed["memory_kind"] == "preference"
    assert confirmed["value"] == {"role": "Java Backend Intern"}
    assert confirmed["source_ref"]["agent_run_id"] == "chat-1"
    assert [memory["key"] for memory in active_after] == ["target_role"]
    assert pending_count == 0
