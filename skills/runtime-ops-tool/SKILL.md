---
name: runtime-ops-tool
description: Use when starting, stopping, rebuilding, or diagnosing the InternAgent Docker Compose runtime, API health, nginx routing, frontend container, or local service recovery.
---

# Runtime Ops Tool

## Tool Contract
Use this skill for host-level runtime control. This skill has no application-data Python script because Docker Compose commands must run on the host, not from inside the API container.

## Script Usage
This skill has no application-data Python script. Use PowerShell from the project root:
```powershell
$env:COMPOSE_BAKE='false'
docker compose up -d --build
docker compose ps
docker compose down
```

## Output Contract
Return command outputs or concise summaries: service name, status, health, exposed ports, and failing logs. Do not print secrets from `.env`.

## Answer Synthesis
Tell the user which services are up, which endpoint was checked, and what command to run next. Distinguish app health from provider health.

## Validation
```powershell
docker compose config
docker compose ps
curl http://localhost/health
```
