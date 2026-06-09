from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from app.services.ai_assistant_file_memory import AIMemoryFileService
from app.services.dream_memory_service import DreamMemoryService


def _append_history(workspace, payload: dict) -> None:
    history_path = workspace / "memory" / "history.jsonl"
    with history_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def test_dream_runs_two_phase_minimal_updates_and_commits_to_runtime_git(tmp_path) -> None:
    file_memory = AIMemoryFileService(root=tmp_path)
    context = file_memory.read_context(user_id="user-1", session_id="session-1")
    workspace = tmp_path / "users" / "user-1"
    (workspace / "USER.md").write_text("# USER\n\n- Prefers concise replies\n", encoding="utf-8")
    (workspace / "SOUL.md").write_text("# SOUL\n\n- Be direct and honest.\n", encoding="utf-8")
    (workspace / "memory" / "MEMORY.md").write_text(
        "# MEMORY\n\n- Existing stable project fact.\n- Prefers concise replies\n",
        encoding="utf-8",
    )
    _append_history(
        workspace,
        {
            "ts": "2026-06-01T00:00:00+00:00",
            "session_id": "session-1",
            "cursor": 2,
            "summary": "User fact: lives in Shanghai. Decision: use PostgreSQL for auth. "
            "Solution: smaller batches fixed import retry. Event: mock interview on 2026-07-01.",
            "facts": {
                "user_facts": ["Lives in Shanghai"],
                "decisions": ["Use PostgreSQL for auth"],
                "solutions": ["Smaller batches fixed import retry"],
                "events": ["Mock interview on 2026-07-01"],
            },
        },
    )

    result = DreamMemoryService(root=tmp_path).run(user_id="user-1", max_batch_size=20)

    assert result["status"] == "completed"
    assert result["commit_sha"]
    assert "USER.md" in result["changed_files"]
    assert "memory/MEMORY.md" in result["changed_files"]
    assert ".git" in {path.name for path in workspace.iterdir()}
    assert "Phase 1 Analysis" in result["analysis"]
    assert "Lives in Shanghai" in (workspace / "USER.md").read_text(encoding="utf-8")
    memory_text = (workspace / "memory" / "MEMORY.md").read_text(encoding="utf-8")
    assert "- Existing stable project fact." in memory_text
    assert "- Use PostgreSQL for auth" in memory_text
    assert "- Smaller batches fixed import retry" in memory_text
    assert "- Prefers concise replies" not in memory_text
    assert context["workspace"] == str(workspace)


def test_dream_log_and_restore_return_diff_and_restore_previous_state(tmp_path) -> None:
    file_memory = AIMemoryFileService(root=tmp_path)
    file_memory.read_context(user_id="user-1", session_id="session-1")
    workspace = tmp_path / "users" / "user-1"
    _append_history(
        workspace,
        {
            "ts": "2026-06-01T00:00:00+00:00",
            "session_id": "session-1",
            "cursor": 2,
            "summary": "Decision: use Redis for cache.",
            "facts": {"decisions": ["Use Redis for cache"]},
        },
    )
    service = DreamMemoryService(root=tmp_path)
    run_result = service.run(user_id="user-1")

    log_text = service.format_log(user_id="user-1", sha=run_result["commit_sha"])
    restore_result = service.restore(user_id="user-1", sha=run_result["commit_sha"])

    assert "Dream Update" in log_text
    assert "Use Redis for cache" in log_text
    assert "Phase 1 Analysis" in log_text
    assert restore_result["status"] == "restored"
    assert "Use Redis for cache" not in (workspace / "memory" / "MEMORY.md").read_text(encoding="utf-8")
    assert restore_result["commit_sha"]


def test_dream_restore_without_sha_lists_recent_dream_commits(tmp_path) -> None:
    file_memory = AIMemoryFileService(root=tmp_path)
    file_memory.read_context(user_id="user-1", session_id="session-1")
    workspace = tmp_path / "users" / "user-1"
    _append_history(
        workspace,
        {
            "ts": "2026-06-01T00:00:00+00:00",
            "session_id": "session-1",
            "cursor": 2,
            "summary": "Decision: use SQLite for local tests.",
            "facts": {"decisions": ["Use SQLite for local tests"]},
        },
    )
    service = DreamMemoryService(root=tmp_path)
    service.run(user_id="user-1")

    restore_points = service.list_restore_points(user_id="user-1", limit=10)

    assert restore_points
    assert restore_points[0]["sha"]
    assert "Dream update" in restore_points[0]["subject"]


def test_dream_memory_prompt_has_age_labels_without_writing_them_to_disk(tmp_path) -> None:
    file_memory = AIMemoryFileService(root=tmp_path)
    file_memory.read_context(user_id="user-1", session_id="session-1")
    workspace = tmp_path / "users" / "user-1"
    memory_path = workspace / "memory" / "MEMORY.md"
    memory_path.write_text("# MEMORY\n\n- Old but still true project decision\n", encoding="utf-8")
    old_seen_at = (datetime.now(timezone.utc) - timedelta(days=21)).isoformat()
    (workspace / ".dream" / "line_state.json").write_text(
        json.dumps({"memory/MEMORY.md": {"- Old but still true project decision": old_seen_at}}),
        encoding="utf-8",
    )

    prompt = DreamMemoryService(root=tmp_path).build_phase1_prompt(user_id="user-1", history_items=[])

    assert "- Old but still true project decision  \u2190 21d" in prompt
    assert "\u2190" not in memory_path.read_text(encoding="utf-8")
