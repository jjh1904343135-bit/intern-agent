from __future__ import annotations

import json

from app.services.ai_assistant_file_memory import AIMemoryFileService


def test_ai_assistant_file_memory_writes_session_and_reads_long_term_files(tmp_path) -> None:
    service = AIMemoryFileService(root=tmp_path)

    service.append_session_message(
        user_id="user-1",
        session_id="session-1",
        role="user",
        content="我想找北京 Java 后端实习",
        metadata={"intent": "job_search"},
    )
    service.append_session_message(
        user_id="user-1",
        session_id="session-1",
        role="assistant",
        content="可以，我会优先找北京 Java 后端实习并解释匹配原因。",
        metadata={"source": "mock"},
    )

    context = service.read_context(user_id="user-1", session_id="session-1")
    session_file = tmp_path / "users" / "user-1" / "sessions" / "session-1.jsonl"

    assert session_file.exists()
    assert context["session_recent"][-1]["role"] == "assistant"
    assert {item["name"] for item in context["files_used"]} >= {"USER.md", "MEMORY.md", "SOUL.md", "session"}
    assert (tmp_path / "users" / "user-1" / "USER.md").exists()
    assert (tmp_path / "users" / "user-1" / "MEMORY.md").exists()
    assert (tmp_path / "users" / "user-1" / "SOUL.md").exists()


def test_ai_assistant_file_memory_soft_consolidates_without_deleting_raw_session(tmp_path) -> None:
    service = AIMemoryFileService(root=tmp_path, consolidation_char_limit=120, keep_recent_messages=1)
    for index in range(5):
        service.append_session_message(
            user_id="user-1",
            session_id="session-1",
            role="user" if index % 2 == 0 else "assistant",
            content=f"第 {index} 条很长的求职偏好内容，目标城市北京，目标岗位 Java 后端。",
            metadata={"index": index},
        )

    summary = service.soft_consolidate(user_id="user-1", session_id="session-1")
    history_file = tmp_path / "users" / "user-1" / "memory" / "history.jsonl"
    session_file = tmp_path / "users" / "user-1" / "sessions" / "session-1.jsonl"

    assert summary["compacted"] is True
    assert history_file.exists()
    history_item = json.loads(history_file.read_text(encoding="utf-8").splitlines()[0])
    assert history_item["session_id"] == "session-1"
    assert "北京" in history_item["summary"]
    assert len(session_file.read_text(encoding="utf-8").splitlines()) == 5


def test_ai_assistant_dream_updates_long_term_markdown_from_history(tmp_path) -> None:
    service = AIMemoryFileService(root=tmp_path, consolidation_char_limit=80, keep_recent_messages=1)
    service.append_session_message(
        user_id="user-1",
        session_id="session-1",
        role="user",
        content="我偏好北京和上海的 Java 后端岗位，也关注腾讯。" * 4,
    )
    service.append_session_message(user_id="user-1", session_id="session-1", role="assistant", content="已记录你的求职偏好。")
    service.soft_consolidate(user_id="user-1", session_id="session-1")

    result = service.dream_update(user_id="user-1")

    assert "USER.md" in result["updated_files"]
    assert "北京" in (tmp_path / "users" / "user-1" / "USER.md").read_text(encoding="utf-8")
    assert result["history_items_read"] >= 1
