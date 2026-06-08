---
name: application-list-tool
description: Use when reading saved jobs, application status counts, manual follow-up notes, or the user's application tracking state.
---

# Application List Tool

## Tool Contract
Use this skill to inspect the manual application workflow through `ApplicationService.list_applications`. It reads saved/opened/applied/waiting/interviewing/closed states only. It never performs external submission.

## Script Usage
Run inside the API container:
```powershell
docker compose exec api python /app/skills/application-list-tool/scripts/list_applications.py --email admin@example.com
```
Inputs: `--user-id` or `--email`, optional `--limit`.

## Output Contract
The script emits compact JSON: `total`, `statuses`, and `items[]` with `application_id`, `status`, `job`, and `tracking_notes`. Missing users return `ok=true` with zero records.

## Answer Synthesis
Summarize next follow-up actions by status. Make clear the user must apply on the original site and manually confirm state changes.

## Validation
```powershell
python skills/application-list-tool/scripts/list_applications.py --self-test
python skills/application-list-tool/scripts/list_applications.py --help
docker compose exec api python /app/skills/application-list-tool/scripts/list_applications.py --email admin@example.com
```
