# Qingcheng AI Project Standards Review

Date: 2026-06-09

Scope: this review intentionally does not evaluate product features. It focuses on repository standards, handoff clarity, source/document boundaries, Markdown hygiene, and whether a new maintainer can clone the project and understand where to start.

## Executive Summary

The project has a recognizable backend/frontend/test structure, but the repository boundary is not clean enough for handoff. The biggest issue is that important source code, generated/runtime data, project-specific agent instructions, third-party knowledge material, and historical process notes are mixed in the same top-level view. A new maintainer can see many files, but cannot quickly tell which ones are authoritative.

The most urgent standards issue found in this pass was a `.gitignore` rule that ignored `backend/app/agents/runtime/`, even though tracked code imports `app.agents.runtime`. That means a clean clone could miss a required source package. This review fixes the ignore rule and adds the runtime source package to Git.

## High-Priority Standards Issues

1. Source code was accidentally ignored.
   `.gitignore` used an unanchored `runtime/` rule, which matched `backend/app/agents/runtime/`. Meanwhile tracked files import `app.agents.runtime`, for example `backend/app/services/chat_service.py` and multiple tests under `backend/tests/agents/`. This makes the repository unreliable after clone.
   Status: fixed in this review by changing the ignore rule to `/runtime/` and adding `backend/app/agents/runtime/`.

2. Documentation points at paths that are stale, missing, or not tracked.
   `README.md` points new readers to `agents/runtime/lifecycle.py`; `docs/architecture/project-map.md` points to `backend/app/agents/runtime/`; and `docs/architecture/agent-learning-route.md` points to `backend/app/agents/runtime/lifecycle.py`. Those references only become valid after the ignore-rule fix. The same docs also mention paths such as `backend/app/prompts/templates/rag/` and `docs/resume/internagent-agent-resume.tex`, which are not present in the tracked tree.

3. Root documentation is overloaded.
   `README.md` currently combines product description, feature inventory, architecture, local startup, API notes, learning path, protocol notes, and dated architecture updates. It is useful as a memory dump, but not as a clean entry document. A handoff-friendly README should be shorter and delegate details to stable docs.

4. Local agent workflow rules are mixed into project source.
   `AGENT_RULES.md` tells an assistant to read `AGENT_RULES.md`, `PROGRESS.md`, and every `skills/*/SKILL.md` before each resumed task. That may be useful for a local AI workflow, but it is not a general contributor standard. It should be moved under an explicit internal tooling area, or renamed so humans do not mistake it for engineering policy.

5. Formatting and quality tooling is incomplete.
   `.editorconfig` exists, but there is no `pyproject.toml`, `ruff.toml`, `mypy.ini`, `eslint.config.*`, Prettier config, Makefile, CI workflow, or unified check command. The frontend has `test`, `typecheck`, and `build` scripts, but no lint/format scripts. The backend has `pytest.ini`, but no linter/type-checker configuration. This leaves style and import hygiene dependent on manual discipline.

6. Generated, cached, and source-like files are too close together.
   The working tree contains ignored local state such as `.venv/`, `.pytest_cache/`, `.tmp/`, `frontend/.next/`, `frontend/node_modules/`, and `backend/test_chat_langgraph.db`. They are mostly ignored correctly, but their presence at the project root makes local review noisy. More importantly, tracked files also include evaluation reports and knowledge-source Markdown, which look like source docs even when they are generated or external corpus material.

7. Branch and commit hygiene is weak.
   Local `main` had no upstream configured, and the working tree already contained uncommitted chat_graph/chat refactor changes before this review. That makes it hard to separate stable repository state from local experiments. A handoff-ready repo should use small branches/PRs, keep `main` clean, and avoid long-lived dirty working trees.

## Markdown Files That Are Not Suitable As-Is

These files are not all "bad"; the issue is that their current location or format makes the project harder to understand.

1. `方法.md`
   Root-level Chinese filename with no project-specific title or ownership. The content reads like an external memory-system note, not InternAgent documentation. It should be removed from root, renamed and moved under `docs/research/`, or deleted if it is only personal reference material.

2. `PROGRESS.md`
   This is a long chronological development log. It duplicates README/project-review content and is not a stable contributor entry point. Keep it only as `docs/archive/progress-log.md`, or replace it with a short `CHANGELOG.md` plus milestone summaries.

3. `AGENT_RULES.md`
   Useful for local assistant behavior, but unsuitable as a top-level project standard because it asks every restored task to read all skill files. Move it to something like `docs/internal/agent-workflow.md` or `.codex/AGENT_RULES.md` if it is meant for tooling.

4. `docs/project-review-status.md`
   The document says the current directory is not a Git repository, and it references a resume file under `docs/resume/` that is not tracked. It should be refreshed or replaced by this standards review plus a shorter status document.

5. `docs/architecture/agent-learning-route.md`
   The file is useful in intent, but it is encoding-sensitive on Windows tooling and includes stale runtime-path references. It should be rewritten as a stable onboarding route, not a dated interview script.

6. `docs/architecture/project-map.md`
   Good idea, but currently mixes evergreen architecture with "this round added" notes and references some paths that are absent. Keep it, but make it generated from the actual tree or review it before every push.

7. `backend/evals/rag/rag_eval_report.md`
   This looks like generated output. Generated reports should either be under `artifacts/` and ignored, or be committed as dated snapshots such as `docs/evaluation/rag-eval-2026-06-04.md`.

8. `docs/evaluation/agent-rag-eval-report.md`
   This is also a report-style artifact. It should declare when it was generated, from which command, and whether it is a stable benchmark snapshot or just local output.

9. `docs/superpowers/**`
   These are process-plan/spec artifacts. They are useful history, but they are not the first thing a maintainer should see. Move completed plans/specs to `docs/archive/superpowers/` or keep only active specs.

10. `file/knowledge_sources/javaup/**/*.md`
    There are 59 tracked third-party knowledge-source Markdown files. They are corpus data, not project documentation. If kept, they need a clear provenance/license note and should live under a data/fixture path with a manifest. Otherwise, download them through the ingestion script and keep them out of the repo.

11. `skills/*/SKILL.md`
    These are project-specific assistant tool contracts. They can stay if the repo intentionally ships AI-operation tooling, but they should be documented as internal tooling and separated from human-facing docs. Without that boundary, the repo reads like an application mixed with assistant prompt infrastructure.

12. Mixed Markdown encoding
    Some root docs have a UTF-8 BOM while many docs and skills do not. On Windows PowerShell this can make files such as `PROGRESS.md`, `方法.md`, and `docs/architecture/agent-learning-route.md` display as mojibake unless the reader forces UTF-8. Pick one encoding policy and enforce it. `.editorconfig` currently says `charset = utf-8`, but the team should also standardize editor behavior and avoid mixed BOM/no-BOM surprises.

## Recommended Repository Shape

Use the root only for files a new maintainer expects immediately:

```text
README.md
CHANGELOG.md
CONTRIBUTING.md
docker-compose.yml
.env.example
.editorconfig
backend/
frontend/
infra/
docs/
```

Then classify everything else:

- `docs/architecture/`: evergreen architecture maps and onboarding paths.
- `docs/evaluation/`: dated, reproducible benchmark snapshots.
- `docs/security/`: security and compliance boundaries.
- `docs/archive/`: historical plans, progress logs, and completed specs.
- `data/knowledge_sources/` or `fixtures/knowledge_sources/`: small, licensed sample corpora only.
- `skills/`: keep only if this repo intentionally includes assistant tooling; otherwise move to internal tooling.
- `artifacts/`, `runtime/`, caches, local databases, build outputs: ignored and never presented as source.

## Concrete Cleanup Order

1. Keep `main` clean: commit or discard the existing chat_graph/chat refactor on its own branch.
2. Add CI with backend tests and frontend typecheck/test/build.
3. Add Python lint/format config and frontend lint/format config.
4. Trim `README.md` to an entry point and move dated details into docs.
5. Move or remove `方法.md`, archive `PROGRESS.md`, and refresh `docs/project-review-status.md`.
6. Decide whether `skills/` is first-class project tooling or private assistant tooling, then document that decision.
7. Decide whether the JavaUp Markdown corpus belongs in Git; if yes, add provenance/license notes and keep it out of human-facing docs navigation.
