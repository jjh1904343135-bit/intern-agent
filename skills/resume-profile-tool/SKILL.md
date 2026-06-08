---
name: resume-profile-tool
description: Use when reading a user's default resume profile, resume parse status, resume score, rubric dimensions, risks, or skills for Agent context.
---

# Resume Profile Tool

## Tool Contract
Use this skill to inspect resume facts already stored by InternAgent. It reads `ResumeRepository` and returns a compact profile. It must not return full `raw_text`, full resume contents, uploaded file bytes, or private prompt context.

## Script Usage
Run inside the API container:
```powershell
docker compose exec api python /app/skills/resume-profile-tool/scripts/inspect_resume_profile.py --email admin@example.com
```
Inputs: `--user-id` or `--email`, optional `--latest`.

## Output Contract
The script emits compact JSON: `available`, `resume_id`, `file_name`, `parse_status`, `score`, `rubric_version`, `risks`, `skills`, `dimension_count`, `has_raw_text`. Missing users or resumes return `ok=true` with `available=false`.

## Answer Synthesis
Use the score, risks, and skills to answer what the Agent knows about the candidate. Say explicitly when no parsed/default resume is available. Do not invent experience beyond returned fields.

## Validation
```powershell
python skills/resume-profile-tool/scripts/inspect_resume_profile.py --self-test
python skills/resume-profile-tool/scripts/inspect_resume_profile.py --help
docker compose exec api python /app/skills/resume-profile-tool/scripts/inspect_resume_profile.py --email admin@example.com
```
