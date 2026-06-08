from __future__ import annotations

from pathlib import Path

import pytest

from app.services.assistant_memory_markdown_service import AssistantMemoryMarkdownService


USER_ID = "11111111-1111-1111-1111-111111111111"


def test_format_snapshot_uses_safe_summaries_and_metadata(tmp_path: Path) -> None:
    service = AssistantMemoryMarkdownService(runtime_root=tmp_path)

    markdown = service.format_snapshot(
        user_id=USER_ID,
        assistant_type="ai_assistant",
        memories=[
            {
                "scope_type": "global",
                "memory_kind": "goal",
                "key": "last_intent",
                "summary": "Recent intent: job_search",
                "confidence": 0.75,
                "source": "chat_turn",
                "source_ref": {"request_id": "req-1", "raw_prompt": "secret prompt"},
                "value": {"raw_text": "full resume"},
            }
        ],
    )

    assert "version: memory_snapshot_v1" in markdown
    assert f'user_id: "{USER_ID}"' in markdown
    assert 'assistant_type: "ai_assistant"' in markdown
    assert "`goal:last_intent` confidence=0.75 source=chat_turn" in markdown
    assert "Recent intent: job_search" in markdown
    assert "secret prompt" not in markdown
    assert "full resume" not in markdown
    assert "raw_prompt" not in markdown


def test_snapshot_path_rejects_invalid_identity(tmp_path: Path) -> None:
    service = AssistantMemoryMarkdownService(runtime_root=tmp_path)

    with pytest.raises(ValueError):
        service.snapshot_path(user_id="../escape", assistant_type="ai_assistant")

    with pytest.raises(ValueError):
        service.snapshot_path(user_id=USER_ID, assistant_type="../bad")


def test_write_and_read_snapshot_round_trip(tmp_path: Path) -> None:
    service = AssistantMemoryMarkdownService(runtime_root=tmp_path)

    result = service.write_snapshot(
        user_id=USER_ID,
        assistant_type="interview_assistant",
        memories=[
            {
                "scope_type": "global",
                "memory_kind": "interview_pattern",
                "key": "latest_interview_summary",
                "summary": "Recent mock interview pass probability: medium.",
                "confidence": 0.82,
                "source": "interview_summary",
            }
        ],
    )
    loaded = service.read_snapshot(user_id=USER_ID, assistant_type="interview_assistant")

    assert result["available"] is True
    assert result["assistant_type"] == "interview_assistant"
    assert result["item_count"] == 1
    assert result["path"].endswith("/interview_assistant.md")
    assert loaded["available"] is True
    assert "Recent mock interview pass probability: medium." in loaded["content"]
