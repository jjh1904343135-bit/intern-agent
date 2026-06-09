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
