from __future__ import annotations

import json

from app.services.ai_assistant_file_memory import AIMemoryFileService


def test_ai_assistant_file_memory_creates_five_layer_workspace(tmp_path) -> None:
    service = AIMemoryFileService(root=tmp_path)

    service.append_session_message(
        user_id="user-1",
        session_id="session-1",
        role="user",
        content="I prefer concise replies and I am targeting backend internships.",
        metadata={"intent": "job_search"},
    )

    context = service.read_context(user_id="user-1", session_id="session-1")
    workspace = tmp_path / "users" / "user-1"

    assert (workspace / "sessions" / "session-1.jsonl").exists()
    assert (workspace / "memory" / "history.jsonl").exists()
    assert (workspace / "memory" / "MEMORY.md").exists()
    assert (workspace / "USER.md").exists()
    assert (workspace / "SOUL.md").exists()
    assert (workspace / ".dream" / "state.json").exists()
    assert not (workspace / "MEMORY.md").exists()
    assert context["session_recent"][-1]["role"] == "user"
    assert {item["name"] for item in context["files_used"]} >= {
        "USER.md",
        "SOUL.md",
        "memory/MEMORY.md",
        "memory/history.jsonl",
        "session",
    }


def test_ai_assistant_file_memory_migrates_legacy_root_memory_md(tmp_path) -> None:
    workspace = tmp_path / "users" / "user-1"
    workspace.mkdir(parents=True)
    (workspace / "MEMORY.md").write_text("# MEMORY\n\n- legacy project decision\n", encoding="utf-8")

    service = AIMemoryFileService(root=tmp_path)
    service.read_context(user_id="user-1", session_id="session-1")

    assert not (workspace / "MEMORY.md").exists()
    assert "legacy project decision" in (workspace / "memory" / "MEMORY.md").read_text(encoding="utf-8")


def test_ai_assistant_file_memory_soft_consolidates_without_deleting_raw_session(tmp_path) -> None:
    service = AIMemoryFileService(root=tmp_path, consolidation_char_limit=120, keep_recent_messages=1)
    for index in range(5):
        service.append_session_message(
            user_id="user-1",
            session_id="session-1",
            role="user" if index % 2 == 0 else "assistant",
            content=f"turn {index}: user prefers concise replies. Decision: use PostgreSQL for auth. "
            "Solution: smaller batches fixed the import retry.",
            metadata={"index": index},
        )

    summary = service.soft_consolidate(user_id="user-1", session_id="session-1")
    history_file = tmp_path / "users" / "user-1" / "memory" / "history.jsonl"
    session_file = tmp_path / "users" / "user-1" / "sessions" / "session-1.jsonl"

    assert summary["compacted"] is True
    history_item = json.loads(history_file.read_text(encoding="utf-8").splitlines()[0])
    assert history_item["session_id"] == "session-1"
    assert history_item["cursor"] == 4
    assert "PostgreSQL" in history_item["summary"]
    assert history_item["facts"]["decisions"]
    assert history_item["facts"]["solutions"]
    assert len(session_file.read_text(encoding="utf-8").splitlines()) == 5


def test_ai_assistant_file_memory_force_consolidates_when_chat_context_is_compressed(tmp_path) -> None:
    service = AIMemoryFileService(root=tmp_path, consolidation_char_limit=999999, keep_recent_messages=2)
    for index in range(7):
        service.append_session_message(
            user_id="user-1",
            session_id="session-1",
            role="user",
            content=f"turn {index}: Event: interview deadline is 2026-07-{index + 10}.",
        )

    result = service.soft_consolidate(user_id="user-1", session_id="session-1", force=True)

    assert result["compacted"] is True
    assert result["cursor"] == 5
    assert result["message_count"] == 5
