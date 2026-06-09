# Qingcheng AI / InternAgent

Qingcheng AI is a local AI job-search workbench for resume parsing, job discovery, application tracking, chat assistance, interview practice, RAG, and Telegram task notifications.

This repository is now organized as an engineering project first. The root README is only the entry point; detailed architecture, evaluation, and safety notes live under `docs/`.

## Stack

- Backend: FastAPI, SQLAlchemy, Alembic, PostgreSQL, Redis, Qdrant
- Frontend: Next.js 14, TypeScript, Tailwind CSS, Vitest
- AI runtime: controlled Python agent layer with allowlisted tools
- Local runtime: Docker Compose

## Repository Layout

```text
backend/        FastAPI app, agents, services, repositories, migrations, tests
frontend/       Next.js app, UI components, frontend tests
infra/          nginx and SQL bootstrap files
docs/           architecture, evaluation, safety, and standards notes
file/           local knowledge-source corpus used by RAG ingestion
skills/         project-specific assistant/tool contracts
docker-compose.yml
.env.example
CONTRIBUTING.md
```

## Start Locally

```powershell
Copy-Item .env.example .env -Force
$env:COMPOSE_BAKE='false'
docker compose up -d --build
```

Main local URLs:

- Frontend: `http://localhost:3000`
- API health: `http://localhost:8000/health`

## Common Checks

Backend:

```powershell
cd backend
python -m compileall -q app
pytest -q
```

Frontend:

```powershell
cd frontend
npm test
npm run typecheck
npm run build
```

Docker-level checks:

```powershell
docker compose exec api pytest -q
docker compose exec api python -m evals.rag.eval_knowledge_rag
docker compose exec api python -m evals.agent.run_agent_eval
```

## Development Standards

Read [CONTRIBUTING.md](CONTRIBUTING.md) before changing code. It defines:

- what belongs in Git and what is local runtime state;
- backend/frontend code style;
- how to place docs and generated reports;
- the minimum checks before committing.

## Useful Docs

- [Project map](docs/architecture/project-map.md)
- [Agent learning route](docs/architecture/agent-learning-route.md)
- [LLM risk boundaries](docs/security/llm-risk-boundaries.md)
- [Agent/RAG evaluation notes](docs/evaluation/agent-rag-eval-report.md)
- [Interview agent story](docs/evaluation/interview-agent-story.md)
- [Repository standards review](docs/project-standards-review.md)
