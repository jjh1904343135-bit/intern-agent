---
name: backend-service-tool
description: Use when inspecting FastAPI routes, controllers, backend service boundaries, repository-backed endpoints, API surface, or route availability.
---

# Backend Service Tool

## Tool Contract
Use this skill to inspect backend API surface without reading every controller. It imports `app.main.app` and lists FastAPI routes and methods.

## Script Usage
Run inside the API container:
```powershell
docker compose exec api python /app/skills/backend-service-tool/scripts/list_routes.py --prefix /api/v1/jobs
```
Inputs: optional `--prefix`.

## Output Contract
The script emits compact JSON: `total` and `routes[]` with `path`, `name`, and `methods`. It does not execute endpoint handlers or mutate data.

## Answer Synthesis
Group routes by domain and mention available methods. If a route is missing, say it is not registered rather than guessing it exists elsewhere.

## Validation
```powershell
python skills/backend-service-tool/scripts/list_routes.py --self-test
python skills/backend-service-tool/scripts/list_routes.py --help
docker compose exec api python /app/skills/backend-service-tool/scripts/list_routes.py --prefix /api/v1
```
