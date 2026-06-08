---
name: interview-state-tool
description: Use when inspecting simulated interview Agent short-term session state, job-resume binding, question plan progress, answer signals, difficulty, follow-up strategy, or remaining focus.
---

# Interview State Tool

## Tool Contract
Use this skill to inspect `interview_sessions.report.agent_state`. The state story is `JobProfile -> CandidateProfile -> QuestionPlan -> AskedQuestions -> AnswerSignals -> EvaluationState -> FollowupStrategy -> SummaryReport`.

Current memory boundary:

- Interview assistant uses current-session short-term memory only.
- It does not read AI assistant file memory.
- It does not write complex long-term `assistant_memories` records.
- Long sessions may compress older turns into `agent_state.session_summary` inside the same interview session.

## Script Usage
Run inside the API container:
```powershell
docker compose exec api python /app/skills/interview-state-tool/scripts/inspect_interview_state.py --email admin@example.com
```
Inputs: optional `--session-id`, optional `--user-id` or `--email`. Without `--session-id`, the latest user session is inspected.

## Output Contract
The script emits compact JSON: `available`, `session_id`, `job_id`, `resume_id`, `mode`, `message_count`, `has_agent_state`, `difficulty`, `remaining_focus`, `last_followup_strategy`, `asked_count`, and `state_keys`. It does not expose hidden reasoning or full message transcripts.

## Answer Synthesis
Explain where the interview currently is, what focus remains, and why the next follow-up may change. If no state exists, tell the user to start or resume a bound interview session.

## Validation
```powershell
python skills/interview-state-tool/scripts/inspect_interview_state.py --self-test
python skills/interview-state-tool/scripts/inspect_interview_state.py --help
docker compose exec api python /app/skills/interview-state-tool/scripts/inspect_interview_state.py --email admin@example.com
docker compose exec api pytest tests/interview/test_interview_short_memory.py -q
```
