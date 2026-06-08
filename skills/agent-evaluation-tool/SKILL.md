---
name: agent-evaluation-tool
description: Use when running Agent golden-case evaluation, checking intent accuracy, tool-call accuracy, RAG grounding, job matching, interview follow-up policy, or resume rubric compliance.
---

# Agent Evaluation Tool

## Tool Contract
Use this skill to run the project golden-case evaluator without relying on API 200s. It calls `evals.agent.run_agent_eval` and reports metrics for intent, tool routing, arguments, RAG grounding, job recommendations, interview follow-ups, and resume rubrics.

## Script Usage
Run inside the API container:
```powershell
docker compose exec api python /app/skills/agent-evaluation-tool/scripts/run_agent_eval.py
```
Inputs: optional `--write-report` to update `docs/evaluation/agent-rag-eval-report.md`.

## Output Contract
The script emits compact JSON: `summary.case_count`, `summary.metrics`, `summary.failed_cases`, and optional `report_path`. If failed cases exist, the script exits with code `2`.

## Answer Synthesis
Lead with failed cases if any, then summarize the most relevant metrics. Do not treat passing evals as proof that live model calls or external providers are healthy.

## Validation
```powershell
python skills/agent-evaluation-tool/scripts/run_agent_eval.py --self-test
python skills/agent-evaluation-tool/scripts/run_agent_eval.py --help
docker compose exec api python /app/skills/agent-evaluation-tool/scripts/run_agent_eval.py
```
