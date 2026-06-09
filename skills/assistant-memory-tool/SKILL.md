---
name: assistant-memory-tool
description: Use when inspecting AI assistant file-based long-term memory, session JSONL archives, soft consolidation, Dream updates, or assistant context isolation.
---

# Assistant Memory Tool

## Tool Contract
AI assistant memory follows the file workspace design implemented in `backend/app/services/ai_assistant_file_memory.py`, while PostgreSQL `chat_sessions` remains the business source of truth.

Runtime path:
```text
runtime/ai_assistant_memory/users/<user_id>/
  sessions/<session_id>.jsonl
  memory/history.jsonl
  USER.md
  MEMORY.md
  SOUL.md
```

Use this skill to inspect the memory boundary:

- AI assistant can read its own session JSONL, history summaries, USER/MEMORY/SOUL files.
- Interview assistant must not read AI assistant file memory.
- Interview assistant no longer writes complex long-term memory; it keeps short-term state inside `interview_sessions.report.agent_state`.
- Soft consolidation appends summaries to `memory/history.jsonl`; it does not overwrite raw `sessions/*.jsonl`.
- Dream updates are minimal local edits to USER/MEMORY/SOUL; no git commit or hidden reasoning exposure.

Legacy `assistant_memories` scripts still exist for older audit data, but the current AI assistant runtime context comes from `runtime/ai_assistant_memory`.

## Script Usage
Inspect legacy database memories if needed:
```powershell
docker compose exec api python /app/skills/assistant-memory-tool/scripts/inspect_memory.py --email admin@example.com --assistant-type ai_assistant
```

Export older database memory snapshots if needed:
```powershell
docker compose exec api python /app/skills/assistant-memory-tool/scripts/export_memory_md.py --email admin@example.com --assistant-type ai_assistant
```

Inspect current file memory from the host or container:
```powershell
Get-ChildItem runtime\ai_assistant_memory\users -Recurse
```

## Output Contract
When reporting current runtime memory, summarize file names, item counts, and whether consolidation happened. Do not print full private messages, raw prompts, API keys, or complete resume text.

## Answer Synthesis
Explain memory as lightweight context, not authoritative fact. The authoritative records remain PostgreSQL users, resumes, jobs, applications, chat_sessions, and interview_sessions. Mention explicitly that the two assistants are isolated: AI assistant file memory is not interview memory.

## Validation
```powershell
python skills/assistant-memory-tool/scripts/inspect_memory.py --self-test
python skills/assistant-memory-tool/scripts/export_memory_md.py --self-test
docker compose exec api pytest tests/memory/test_ai_assistant_file_memory.py tests/interview/test_interview_short_memory.py -q
```
