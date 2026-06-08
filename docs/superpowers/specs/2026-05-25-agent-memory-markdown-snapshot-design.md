# Agent Memory Markdown Snapshot Design

## Goal

Build a product-level long-term memory capability that the InternAgent assistants can actually use at runtime. The memory system should let the AI assistant and interview assistant persist useful user context, render it into a Markdown snapshot that is easy for an LLM to read, and inject that snapshot into later turns without exposing private raw data.

This is not a project notes feature. It is part of the application behavior: remembering job preferences, recent career goals, and interview performance patterns for each user.

## Current Context

The project already has a structured long-term memory store:

- `assistant_memories` stores durable memory rows by `user_id`, `assistant_type`, `scope_type`, `scope_id`, `memory_kind`, `key`, `value`, `summary`, `confidence`, `source`, and `source_ref`.
- `AssistantMemoryRepository` supports upsert, active listing, pending memory candidates, confirmation, soft delete, expiration checks, and compaction.
- `ChatService` writes AI assistant memories such as `last_intent` and `job_search_preference`.
- `InterviewService` writes interview assistant memories such as `latest_interview_summary`.
- `citation_v1` sanitizes memory references before they appear in metadata.

The missing piece is an LLM-readable runtime projection. Today the assistant reads structured memory items directly from the repository; it does not maintain a Markdown memory snapshot similar to Claude-style memory files.

## Recommended Approach

Use a hybrid memory design:

1. PostgreSQL remains the source of truth.
2. Markdown files become sanitized, derived runtime snapshots.
3. Chat and interview flows load the Markdown snapshot before reasoning.
4. Scripts and skills expose inspection/export commands for validation and demos.

This keeps the feature easy to explain in interviews:

- Database: reliable multi-user storage, isolation, deletion, confidence, source trace, and compaction.
- Markdown: LLM-readable long-term memory context that can be injected into prompts.

## Alternatives Considered

### Markdown Only

This is simple and resembles local-agent memory, but it is weak for this product. It would make user isolation, concurrent writes, deletion, expiration, source audit, and scoped queries harder. It is not recommended.

### Database Only

This is what the project mostly has now. It is reliable, but harder to explain as an Agent memory mechanism because the LLM does not visibly consume a stable memory document. It also makes debugging memory context less intuitive.

### Hybrid Snapshot

This is the recommended option. It keeps the current repository model and adds a Markdown projection that the Agent can read. It has low risk because Markdown is derived from existing data instead of replacing existing behavior.

## Architecture

Add a small memory snapshot layer:

- `AssistantMemoryMarkdownService`
  - Reads active memories through `AssistantMemoryRepository`.
  - Formats safe memory summaries as Markdown.
  - Writes snapshots under `/app/runtime/memory/users/<user_id>/<assistant_type>.md`.
  - Reads snapshots for prompt injection.
  - Never writes raw prompts, full resume text, full transcripts, API keys, or Qdrant point IDs.

- `ChatService`
  - After confirming memory updates, refreshes the `ai_assistant.md` snapshot.
  - Before agent planning/reasoning, loads the snapshot and adds it to the memory context.

- `InterviewService`
  - After writing interview summary memory, refreshes the `interview_assistant.md` snapshot.
  - Before interview reasoning, loads the snapshot and adds it to the memory context.

- `assistant-memory-tool`
  - Keeps `inspect_memory.py`.
  - Adds `export_memory_md.py` for explicit smoke tests and demos.

## Runtime File Layout

Memory snapshots live in the existing Docker runtime volume, not in the repository:

```text
/app/runtime/memory/
  users/
    <user_id>/
      ai_assistant.md
      interview_assistant.md
```

The host already mounts the `runtime_data` volume to `/app/runtime` for API and worker containers. This keeps user memory out of source control.

## Markdown Format

Each snapshot is compact and deterministic:

```markdown
---
version: memory_snapshot_v1
user_id: "<uuid>"
assistant_type: "ai_assistant"
generated_at: "2026-05-25T12:00:00Z"
source: "assistant_memories"
count: 2
---

# Long-Term Memory

## Global

- `goal:last_intent` confidence=0.75 source=chat_turn
  Recent AI assistant intent: job_search.

- `application_preference:job_search_preference` confidence=0.70 source=job_search_tool
  The user recently focused on Java backend roles in Beijing with Java and Spring Boot skills.
```

Rules:

- Use only `summary` plus safe metadata.
- Do not include full `value` unless a specific allowlist is added later.
- Sort by `scope_type`, `memory_kind`, `key`, then newest update.
- Keep the file short enough for prompt injection, with a configurable item limit.

## Data Flow

### Write Path

1. User chats or completes an interview turn.
2. Existing service extracts memory candidates.
3. Repository stages and confirms durable memory.
4. Repository may compact old memories.
5. Markdown snapshot service exports active memories for that user and assistant type.
6. SSE metadata reports memory update status and snapshot availability.

### Read Path

1. A new chat or interview turn starts.
2. Service loads structured memory from `assistant_memories`.
3. Service also loads the Markdown snapshot.
4. The prompt receives a bounded "Long-term memory snapshot" section.
5. The LLM treats memory as user context, not as instructions.

## Safety Boundaries

- Markdown snapshot is derived data, not the source of truth.
- Snapshots are stored in `/app/runtime`, not committed to the repository.
- Snapshot generation sanitizes secrets and skips raw prompt, full resume text, full transcript, uploaded file content, Qdrant point ID, provider payloads, and hidden reasoning.
- AI assistant and interview assistant snapshots remain separate.
- Missing or failed snapshots never break chat or interview streaming; services fall back to structured DB memory.
- Markdown content is labelled as untrusted user-context evidence, not system instruction.

## Error Handling

- Snapshot write failure returns a safe metadata flag such as `memory_snapshot_error`.
- Chat and interview flows continue even when Markdown export fails.
- If the snapshot file is missing, the service can rebuild it from the database.
- Invalid assistant type is rejected.
- File paths are derived from validated `user_id` and `assistant_type`; callers cannot pass arbitrary paths.

## Testing

Add focused tests before implementation:

- Formatter test: active memory rows render deterministic Markdown and exclude unsafe fields.
- Path safety test: snapshot paths are only generated under `/app/runtime/memory/users`.
- Chat integration test: after AI assistant memory update, `ai_assistant.md` exists and metadata reports snapshot status.
- Interview integration test: after interview summary memory, `interview_assistant.md` exists and remains isolated from AI assistant memory.
- Prompt context test: chat/interview memory context includes the Markdown snapshot when present.
- Skill/script smoke test: `export_memory_md.py --help` succeeds and returns compact JSON on export.

Regression commands:

```powershell
docker compose exec api pytest tests/memory tests/chat tests/interview tests/skills -q
docker compose exec api python /app/skills/assistant-memory-tool/scripts/export_memory_md.py --email admin@example.com --assistant-type ai_assistant
docker compose exec api python /app/skills/assistant-memory-tool/scripts/export_memory_md.py --email admin@example.com --assistant-type interview_assistant
```

## Acceptance Criteria

- AI assistant and interview assistant each have isolated Markdown snapshots.
- Snapshots are generated from `assistant_memories`, not hand-written project notes.
- Later turns can load Markdown snapshots as long-term memory context.
- Sensitive data is not written to Markdown.
- Existing database memory behavior still passes all current tests.
- The feature can be demonstrated with one script command and one chat/interview flow.

## Interview Explanation

The concise explanation:

> I use PostgreSQL as the authoritative memory store because the product is multi-user and needs isolation, deletion, confidence, source tracing, and compaction. On top of that I generate a sanitized Markdown snapshot per user and per assistant. Before each turn, the Agent reads that Markdown as long-term user context, then decides which tools to call. So the database gives reliability, while Markdown gives the LLM an easy memory surface.
