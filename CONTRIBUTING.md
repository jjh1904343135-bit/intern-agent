# Contributing And Code Standards

This project should be easy to clone, inspect, test, and hand off. Keep source code, runtime state, generated reports, and personal workflow notes clearly separated.

## Git Hygiene

- Commit related changes together. Do not mix feature work, generated files, and documentation cleanup in one commit.
- Keep `main` clean. Put experiments or large refactors on a branch.
- Do not commit `.env`, local databases, runtime memory, caches, build outputs, or dependency folders.
- If a file is required by imports or tests, make sure it is tracked by Git and not hidden by `.gitignore`.
- Prefer small commits with direct messages such as `Add scheduled task parser tests` or `Clean project docs`.

## Backend Standards

- Keep HTTP details in `backend/app/controllers/`.
- Put business orchestration in `backend/app/services/`.
- Put database access in `backend/app/repositories/`.
- Keep SQLAlchemy tables in `backend/app/models/` and Pydantic contracts in `backend/app/schemas/`.
- Agent code belongs in `backend/app/agents/`; shared runtime primitives belong in `backend/app/agents/runtime/`.
- Avoid template docstrings and decorative comments. Add short comments only for non-obvious business boundaries, safety rules, or external-system behavior.
- Prefer typed function signatures and structured return objects over ad hoc dictionaries when the value crosses module boundaries.

## Frontend Standards

- Keep page routing under `frontend/src/app/`.
- Keep reusable UI in `frontend/src/components/`.
- Keep API calls and auth helpers under `frontend/src/lib/`.
- Add focused tests near the component or library behavior being changed.
- Do not turn operational app screens into marketing pages; the first screen should help the user work.

## Documentation Standards

- `README.md` is the entry point, not a changelog or full project diary.
- Use `CONTRIBUTING.md` for engineering rules.
- Use `docs/architecture/` for stable architecture and onboarding maps.
- Use `docs/security/` for risk and compliance boundaries.
- Use `docs/evaluation/` for reproducible evaluation notes.
- Generated reports should be dated snapshots or ignored artifacts, not ambiguous Markdown files in source folders.
- Third-party knowledge-source Markdown is data, not project documentation. Keep provenance and ingestion behavior clear.
- Personal notes, temporary prompts, and historical planning files should not live at the repository root.

## Checks Before Commit

Run the smallest useful set for your change:

```powershell
python -m compileall -q backend\app
cd backend; pytest -q
cd frontend; npm test
cd frontend; npm run typecheck
cd frontend; npm run build
```

For Agent/RAG changes, also run the relevant evaluation command:

```powershell
docker compose exec api python -m evals.agent.run_agent_eval
docker compose exec api python -m evals.rag.eval_knowledge_rag
```

If Docker is unavailable, say that explicitly in the commit or handoff notes instead of implying the container-level checks passed.
