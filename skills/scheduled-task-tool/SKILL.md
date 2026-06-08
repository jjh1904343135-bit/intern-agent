---
name: scheduled-task-tool
description: Use when creating, listing, testing, or debugging Qingcheng AI scheduled tasks, task inbox results, worker execution, natural-language reminder parsing, or Telegram task commands.
---

# Scheduled Task Tool

## Tool Contract
AI assistant scheduled tasks are application-level jobs stored in PostgreSQL, not OS cron files. The scheduler is run by `notification-worker` through `app.tasks.telegram_tasks.run_scheduled_tasks_once()`.

Supported schedule types:

- `once`: one-time reminders such as `明天上午 9 点提醒我检查投递状态`.
- `interval`: repeated intervals such as `每 30 分钟检查一次岗位`.
- `cron`: five-field cron expressions and common workday phrases such as `工作日早上 9 点提醒我看投递`.
- Natural relative and weekly phrases are supported, for example `一分钟后提醒我看岗位`, `半小时后提醒我检查简历`, and `每周一早上 9 点提醒我检查投递`.

Safety boundary:

- Allowed task tools are project service tools: `chat_answer`, `resume_profile`, `job_search`, `application_list`, `knowledge_search`, `telegram_send`.
- Do not execute shell commands.
- Do not automatically submit external applications.
- Do not bypass login, captcha, slider verification, or recruitment platform anti-bot controls.
- Results are written to `assistant_task_inbox`; Telegram-created tasks also send results back to Telegram.
- Telegram-created tasks must use `source_channel=telegram`, `delivery_channel=telegram`, and `telegram_chat_id`; execution results are sent to the same Telegram chat and also copied to `assistant_task_inbox`.

## Script Usage
This skill has no application-data Python script. Use backend tests, API checks, and worker functions for validation.

Run unit tests from the host:
```powershell
python -m pytest backend/tests/scheduled_tasks -q
```

Run inside Docker after migrations:
```powershell
docker compose exec api pytest tests/scheduled_tasks -q
docker compose exec api python -c "from app.tasks.telegram_tasks import run_scheduled_tasks_once; print(run_scheduled_tasks_once())"
```

API checks:
```powershell
curl http://localhost/api/v1/scheduled-tasks -H "Authorization: Bearer <access_token>"
curl http://localhost/api/v1/task-inbox -H "Authorization: Bearer <access_token>"
```

Telegram commands:
```text
/tasks
/cancel_task <id-prefix>
/pause_task <id-prefix>
/resume_task <id-prefix>
```

## Output Contract
Task API items include `task_id`, `title`, `instruction`, `status`, `schedule_type`, `schedule_label`, `next_run_at`, `next_run_at_local`, `delivery_channel`, and `last_error`.

Inbox API items include `inbox_id`, `task_id`, `task_run_id`, `title`, `content`, `status`, `created_at`, and safe metadata summaries.

Chat SSE `end.metadata` includes `scheduled_task_action`, `scheduled_task_id`, `schedule_summary`, `next_run_at`, `task_inbox_id`, and `tool_calls_summary`.

## Answer Synthesis
When explaining scheduled tasks, say clearly that tasks are persistent, worker-driven, auditable, and scoped to the AI assistant. Do not describe them as operating-system cron or as arbitrary automation with full machine access.

## Validation
```powershell
python -m compileall -q backend/app
python -m pytest backend/tests/scheduled_tasks -q
cd frontend
npm test -- scheduled-task-panel
npm run typecheck
```
