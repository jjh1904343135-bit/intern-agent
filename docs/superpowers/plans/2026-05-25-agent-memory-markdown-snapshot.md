# Agent Memory Markdown Snapshot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add product-level Markdown memory snapshots that AI and interview assistants can read at runtime while keeping PostgreSQL as the authoritative memory store.

**Architecture:** Add a focused `AssistantMemoryMarkdownService` that formats, writes, and reads sanitized Markdown snapshots under `/app/runtime/memory/users/<user_id>/<assistant_type>.md`. Integrate it after memory writes and before prompt construction in `ChatService` and `InterviewService`. Extend `assistant-memory-tool` with an export script and validation contract.

**Tech Stack:** FastAPI backend, SQLAlchemy sessions, PostgreSQL-backed `AssistantMemoryRepository`, pytest, Docker Compose, project skill scripts.

---

## File Structure

- Create `backend/app/services/assistant_memory_markdown_service.py`: snapshot path validation, Markdown formatting, export, and load helpers.
- Modify `backend/app/services/chat_service.py`: refresh and load `ai_assistant` Markdown snapshots.
- Modify `backend/app/services/interview_service.py`: refresh and load `interview_assistant` Markdown snapshots.
- Create `backend/tests/memory/test_assistant_memory_markdown_service.py`: unit tests for formatting, path safety, read/write behavior, and sanitization.
- Modify `backend/tests/chat/test_chat_stream.py`: assert chat metadata includes snapshot status after memory update.
- Modify `backend/tests/interview/test_interview_session.py`: assert interview metadata includes isolated snapshot status.
- Create `skills/assistant-memory-tool/scripts/export_memory_md.py`: command-line export tool.
- Modify `skills/assistant-memory-tool/SKILL.md`: document Markdown snapshot export.
- Modify `backend/tests/skills/test_tool_skills_contract.py`: include the new script in skill contract checks.
- Modify `PROGRESS.md`: record the feature once verified.

## Task 1: Markdown Snapshot Service Tests

**Files:**
- Create: `backend/tests/memory/test_assistant_memory_markdown_service.py`
- Create later: `backend/app/services/assistant_memory_markdown_service.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

import pytest

from app.services.assistant_memory_markdown_service import AssistantMemoryMarkdownService


def test_format_snapshot_uses_safe_summaries_and_metadata(tmp_path: Path) -> None:
    service = AssistantMemoryMarkdownService(runtime_root=tmp_path)
    markdown = service.format_snapshot(
        user_id="11111111-1111-1111-1111-111111111111",
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
    assert "`goal:last_intent` confidence=0.75 source=chat_turn" in markdown
    assert "Recent intent: job_search" in markdown
    assert "secret prompt" not in markdown
    assert "full resume" not in markdown


def test_snapshot_path_rejects_invalid_identity(tmp_path: Path) -> None:
    service = AssistantMemoryMarkdownService(runtime_root=tmp_path)

    with pytest.raises(ValueError):
        service.snapshot_path(user_id="../escape", assistant_type="ai_assistant")

    with pytest.raises(ValueError):
        service.snapshot_path(user_id="11111111-1111-1111-1111-111111111111", assistant_type="../bad")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
docker compose exec api pytest tests/memory/test_assistant_memory_markdown_service.py -q
```

Expected: fail because `app.services.assistant_memory_markdown_service` does not exist.

- [ ] **Step 3: Implement minimal service**

Add `AssistantMemoryMarkdownService` with `snapshot_path`, `format_snapshot`, `write_snapshot`, `read_snapshot`, and `export_snapshot`.

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
docker compose exec api pytest tests/memory/test_assistant_memory_markdown_service.py -q
```

Expected: all tests pass.

## Task 2: Chat Runtime Integration

**Files:**
- Modify: `backend/app/services/chat_service.py`
- Modify: `backend/tests/chat/test_chat_stream.py`

- [ ] **Step 1: Write the failing test**

Add assertions to the existing AI assistant memory namespace test:

```python
assert metadata["memory_snapshot"]["available"] is True
assert metadata["memory_snapshot"]["assistant_type"] == "ai_assistant"
assert metadata["memory_snapshot"]["path"].endswith("/ai_assistant.md")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
docker compose exec api pytest tests/chat/test_chat_stream.py::test_chat_stream_metadata_uses_ai_assistant_memory_namespace -q
```

Expected: fail with missing `memory_snapshot`.

- [ ] **Step 3: Implement chat integration**

Import `AssistantMemoryMarkdownService`, load snapshot in `_load_assistant_memory`, refresh snapshot in `_remember_turn`, and include safe `memory_snapshot` metadata.

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
docker compose exec api pytest tests/chat/test_chat_stream.py::test_chat_stream_metadata_uses_ai_assistant_memory_namespace -q
```

Expected: test passes.

## Task 3: Interview Runtime Integration

**Files:**
- Modify: `backend/app/services/interview_service.py`
- Modify: `backend/tests/interview/test_interview_session.py`

- [ ] **Step 1: Write the failing test**

Add assertions to the existing interview memory namespace test:

```python
assert metadata["memory_snapshot"]["available"] is True
assert metadata["memory_snapshot"]["assistant_type"] == "interview_assistant"
assert metadata["memory_snapshot"]["path"].endswith("/interview_assistant.md")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
docker compose exec api pytest tests/interview/test_interview_session.py::test_interview_stream_metadata_uses_interview_assistant_memory_namespace -q
```

Expected: fail with missing `memory_snapshot`.

- [ ] **Step 3: Implement interview integration**

Import `AssistantMemoryMarkdownService`, load snapshot in `_load_interview_memory`, refresh snapshot in `_remember_interview_turn`, and include safe `memory_snapshot` metadata.

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
docker compose exec api pytest tests/interview/test_interview_session.py::test_interview_stream_metadata_uses_interview_assistant_memory_namespace -q
```

Expected: test passes.

## Task 4: Skill Export Script

**Files:**
- Create: `skills/assistant-memory-tool/scripts/export_memory_md.py`
- Modify: `skills/assistant-memory-tool/SKILL.md`
- Modify: `backend/tests/skills/test_tool_skills_contract.py`

- [ ] **Step 1: Write the failing contract test**

Extend the skill contract so `assistant-memory-tool` requires both `inspect_memory.py` and `export_memory_md.py`.

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
docker compose exec api pytest tests/skills -q
```

Expected: fail because `export_memory_md.py` is missing.

- [ ] **Step 3: Implement export script and docs**

The script resolves user identity, calls `AssistantMemoryMarkdownService.export_snapshot`, and emits compact JSON with `available`, `assistant_type`, `path`, `item_count`, and `char_count`.

- [ ] **Step 4: Run tests and script smoke**

Run:

```powershell
docker compose exec api pytest tests/skills -q
docker compose exec api python /app/skills/assistant-memory-tool/scripts/export_memory_md.py --help
```

Expected: tests and help command pass.

## Task 5: Regression and Documentation

**Files:**
- Modify: `PROGRESS.md`

- [ ] **Step 1: Update progress**

Add a dated entry that describes runtime Markdown memory snapshots for AI and interview assistants.

- [ ] **Step 2: Run targeted backend regression**

Run:

```powershell
docker compose exec api pytest tests/memory tests/chat tests/interview tests/skills -q
```

Expected: all targeted tests pass.

- [ ] **Step 3: Run full backend regression if targeted tests pass**

Run:

```powershell
docker compose exec api pytest -q
```

Expected: full backend test suite passes.

## Self-Review

- The plan covers formatting, storage path safety, runtime read/write integration, skill export, and verification.
- No Markdown-only rewrite is planned; PostgreSQL remains authoritative.
- The plan keeps user snapshots under `/app/runtime`, which is already a Docker volume.
- The plan does not require frontend work because the accepted design only needs runtime Agent memory and script-level demonstration.
