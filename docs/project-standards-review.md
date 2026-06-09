# Project Standards Review

Date: 2026-06-09

This review focuses on repository and code standards, not product features.

## Main Findings

1. The previous repository boundary was unclear.
   Source code, local runtime files, generated reports, personal notes, third-party knowledge material, and assistant workflow files were too close together.

2. A `.gitignore` rule accidentally hid source code.
   The unanchored `runtime/` rule ignored `backend/app/agents/runtime/`, while tracked files imported `app.agents.runtime`. This was fixed by changing the rule to `/runtime/` and tracking the runtime package.

3. Root documentation was too noisy.
   `README.md`, `PROGRESS.md`, `方法.md`, and `AGENT_RULES.md` made it hard to tell which file was the actual project entry point. The root now keeps README and CONTRIBUTING as the human-facing entry files.

4. Code standards were implicit.
   The project had `.editorconfig`, tests, and useful structure, but no clear contributor rules. `CONTRIBUTING.md` now defines Git hygiene, backend/frontend boundaries, documentation placement, and check commands.

5. Generated reports need a policy.
   Generated evaluation output should be ignored or committed as dated, reproducible snapshots. Ambiguous report Markdown inside source folders should not be treated as stable project docs.

## Markdown Cleanup Done

Removed as root clutter or stale process material:

- `方法.md`
- `PROGRESS.md`
- `AGENT_RULES.md`
- `docs/project-review-status.md`
- `docs/superpowers/**`
- `backend/evals/rag/rag_eval_report.md`

Kept because they still describe stable project behavior:

- `docs/architecture/project-map.md`
- `docs/architecture/agent-learning-route.md`
- `docs/security/llm-risk-boundaries.md`
- `docs/evaluation/agent-rag-eval-report.md`
- `docs/evaluation/interview-agent-story.md`

## Remaining Cleanup Worth Doing

1. Decide whether `skills/` is shipped project tooling or private assistant tooling.
2. Add CI for backend tests and frontend test/typecheck/build.
3. Add Python lint/format config and frontend lint/format config.
4. Add provenance/license notes for `file/knowledge_sources/javaup/`.
5. Move large local experiments into branches before pushing them to `main`.

## Chinese-Learner Readability Review

Full manual review cannot be done by loading every file into one model context. The practical workflow is staged:

1. Use repository-wide scans to find large files, missing docstrings, vague names, and broken Markdown.
2. Review high-risk entry files first: `chat_service.py`, `job_service.py`, `interview_service.py`, memory services, and tool adapters.
3. Add module-level Chinese guidance before renaming code, because broad renames can break imports, tests, and external references.
4. Rename only when the existing name is actively misleading.

Current readability findings:

- `docs/architecture/agent-learning-route.md` was not readable Chinese and was rewritten.
- The backend has several large orchestration files that need top-level guidance for new readers.
- Naming is mostly English and structurally consistent, but some names such as `run`, `handle`, and `tool_context` require surrounding explanation for beginners.
- The project should keep identifiers in English for ecosystem compatibility, while using Chinese in documentation, module comments, and learning notes.

Comment policy for this project:

- Explain layer ownership, workflow, and non-obvious business choices.
- Do not translate every line of code.
- Prefer comments like “why this branch exists” over “assign value to variable”.
- Public services, Agent entry points, and long utility modules should have a short Chinese reading note.
