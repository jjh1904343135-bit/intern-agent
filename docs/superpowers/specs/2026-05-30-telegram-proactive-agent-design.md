# Telegram Proactive Agent Design

## Goal
Add Telegram as the first external interaction channel for Qingcheng AI: users can talk to the AI assistant from Telegram, and the system can proactively send useful, timestamped nudges without becoming noisy.

## Fit With Multi-Agent Direction
This makes the project more agentic rather than only web-driven. The web app remains the workbench, while Telegram becomes a communication channel. A proactive notification agent now evaluates candidate events, applies interruption rules, asks the LLM for a `send` or `skip` decision, and records an audit trail.

## Akashic-Inspired Shape
The implementation borrows the useful shape from `akashic-agent` without importing its full runtime:

- `TelegramChannel` maps to `TelegramBridgeService`.
- `message_push` maps to `TelegramBotClient` plus notification delivery.
- `DataGateway` maps to candidate builders such as resume status and application follow-up.
- `ProactiveLoop` maps to `run_proactive_notifications_once()` in the existing worker.
- `ProactiveStateStore` maps to PostgreSQL `notification_events`.

## Initial Candidate Events
The first version supports:

- Resume parsing status: done or failed.
- Application follow-up: saved, opened, applied manually, waiting feedback.

Each candidate carries `event_time`, `event_key`, `event_type`, severity, evidence, and a short message hint.

## Interruption Rules
Before calling the LLM, the rule gate blocks:

- Quiet hours.
- Daily push count over the configured limit.
- Already-sent event keys.
- Same notification type within the cooldown window.

The LLM then decides whether a remaining candidate is worth sending and must output JSON with `decision`, `reason`, `priority`, `message`, and `cooldown_hours`. Send messages are forced to start with the local `HH:MM 提醒：` prefix if the LLM omits a timestamp.

## Operational Model
Telegram is disabled by default. When enabled, the worker polls Telegram updates and proactive notifications. In local development, allowed Telegram chat ids or usernames can send `/start` to bind to `TELEGRAM_DEFAULT_USER_EMAIL`.
