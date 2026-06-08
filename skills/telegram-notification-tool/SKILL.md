---
name: telegram-notification-tool
description: Use when configuring, testing, or explaining Qingcheng AI Telegram binding, AI-assistant chat bridging, proactive notification candidates, LLM send/skip decisions, cooldowns, quiet hours, or Telegram delivery failures.
---

# Telegram Notification Tool

## Tool Contract
Telegram is an AI assistant channel, not an interview channel. A web user generates a one-time bind code, sends `/bind CODE` in Telegram, and then Telegram messages reuse the same `ChatService` pipeline as `/chat`, including simple/agentic routing and AI assistant file memory.

Telegram must not create interview sessions or read interview `agent_state`. Telegram can create and manage AI-assistant scheduled tasks through the same database-backed scheduler as the web chat.

Proactive notifications are event-driven. Current candidates include resume parse completion/failure and stale application follow-up. Do not send daily onboarding or generic check-in messages. Delivery must respect `TELEGRAM_ALLOWED_CHAT_IDS`; test or stale accounts outside the allowlist are skipped.

## Frontend Entry
The web entry is on `/chat` via `TelegramBindCard` in the session sidebar:

- Calls `GET /api/v1/telegram/status` first.
- Shows bound status, masked chat id, and enabled/disabled state when the user is already bound.
- Calls `POST /api/v1/telegram/bind-code`.
- Displays `/bind CODE`.
- Shows expiration time and copy action.
- Keeps copy short; no complex setup panel.

## Script Usage
This skill has no application-data Python script. Use worker functions, API checks, and backend tests for validation.

Use the worker functions from the API container:
```powershell
docker compose exec api python -c "from app.tasks.telegram_tasks import poll_telegram_updates_once; print(poll_telegram_updates_once())"
docker compose exec api python -c "from app.tasks.telegram_tasks import run_proactive_notifications_once; print(run_proactive_notifications_once(force=True))"
curl http://localhost:8000/api/v1/telegram/status -H "Authorization: Bearer <access_token>"
curl -X POST http://localhost:8000/api/v1/telegram/bind-code -H "Authorization: Bearer <access_token>"
```

Required `.env` values:
```env
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_CHAT_IDS=123456789,@username
TELEGRAM_DEFAULT_USER_EMAIL=admin@example.com
TELEGRAM_BIND_CODE_TTL_MINUTES=10
```

## Scheduled Task Commands

Telegram task commands:

- `/tasks`: list active scheduled tasks.
- `/cancel_task <id-prefix>`: cancel a task.
- `/pause_task <id-prefix>`: pause a task.
- `/resume_task <id-prefix>`: resume a task.

Natural language messages such as `每天早上 9 点提醒我看投递状态` also go through `ChatService` and can create tasks. Telegram-created task results are written to the task inbox and sent back to the same Telegram chat.

## Output Contract
The bind-code API returns `code`, `command`, `expires_at`, and `ttl_minutes`; the database stores only `code_hash`. Polling returns processed updates. Proactive notification tick returns sent messages. Do not print bot tokens or raw Telegram payloads.

## Answer Synthesis
Explain chat as: web bind code -> Telegram `/bind CODE` -> sticky `chat_session_id` -> `ChatService` -> Telegram reply. Mention phone commands when useful: `/new`, `/new <message>`, `/current`, `/sessions`, `/use <session-prefix>`, `/tasks`, `/cancel_task`, `/pause_task`, `/resume_task`, `/stop`. Explain proactive notifications as candidate event -> allowlist filter -> rule gate -> LLM `send/skip` -> Telegram delivery -> `notification_events` audit record.

## Validation
```powershell
python -m pytest backend/tests/telegram -q
python -m compileall -q backend/app
docker compose exec api python -c "from app.tasks.telegram_tasks import run_proactive_notifications_once; print(run_proactive_notifications_once(force=True))"
cd frontend
npm test
```
