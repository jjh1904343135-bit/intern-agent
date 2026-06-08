---
name: job-search-tool
description: Use when searching or explaining InternAgent job discovery, recommendation, match scoring, source labels, query expansion, city filters, or missing skills.
---

# Job Search Tool

## Tool Contract
Use this skill to run the project job discovery pipeline through `JobService.discover_jobs`. It reuses repository search, taxonomy, dedupe, recommendation scoring, and resume-aware matching when a user is supplied.

## Script Usage
Run inside the API container:
```powershell
docker compose exec api python /app/skills/job-search-tool/scripts/discover_jobs.py --keyword Java --city 北京 --experience intern --email admin@example.com
```
Inputs: `--keyword`, `--city`, `--experience`, `--skills`, `--limit`, optional `--user-id` or `--email`.

## Output Contract
The script emits compact JSON: `total`, `source_kind`, `fallback_notice`, `query_expansions`, and `jobs[]` with title, company, city, source, URL, recommendation score, matched/missing skills, and priority. It never claims a static fallback is live market evidence.

## Answer Synthesis
Present only returned jobs. Mention source and fallback notices. For resume-aware results, explain matched and missing skills. Never say the system submitted an application.

## Validation
```powershell
python skills/job-search-tool/scripts/discover_jobs.py --self-test
python skills/job-search-tool/scripts/discover_jobs.py --help
docker compose exec api python /app/skills/job-search-tool/scripts/discover_jobs.py --keyword 产品 --city 北京 --limit 5
```
