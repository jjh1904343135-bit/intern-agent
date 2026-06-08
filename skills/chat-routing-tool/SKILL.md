---
name: chat-routing-tool
description: Use when inspecting or explaining Qingcheng AI chat complexity classification, prompt-template injection, SupervisorAgent routing, selected tool allowlists, or agent planning for a user message.
---

# Chat Routing Tool

## Tool Contract
Use this skill to inspect how the AI assistant would route a message. The runtime first classifies the turn as `simple_answer` or `agentic_task`:

- `simple_answer`: direct model answer, no tool execution, no planning.
- `agentic_task`: SupervisorAgent planning, service-side tool allowlist, fact reading, generation, validation, and memory archival.
- `scheduled_task`: handled before normal model generation when the user asks to remind, repeat, list, pause, resume, or cancel scheduled tasks.
- Natural job-search phrases such as `帮我搜一下美团开发岗`, `查一下腾讯 Java 岗`, or `推荐北京后端实习` must route to `agentic_task -> job_search`.
- AI assistant replies should be plain Chinese text. ChatService strips Markdown headings, bold markers, list markers, code fences, and raw debug JSON before streaming and persistence.

Prompt text is loaded through `backend/app/prompts/registry.py` from `backend/app/prompts/templates/`. Do not expose rendered prompts or hidden reasoning.

## Script Usage
Run inside the API container:
```powershell
docker compose exec api python /app/skills/chat-routing-tool/scripts/plan_turn.py --message "帮我找北京 Java 后端实习并结合简历分析"
```
Inputs: `--message`, optional `--history-json`, optional `--tool-context-json`.

## Output Contract
The script emits compact JSON: `ok`, `tool`, `input`, `result.complexity`, `result.intent`, `result.steps`, `result.tools`, `result.prompt_template_id`, `result.prompt_template_version`, `result.prompt_chars`, and `result.system_prompt_chars`. Errors return `ok=false` with `code` and `error`.

## Answer Synthesis
Summarize whether the turn is simple or agentic, then summarize detected intent and selected tools. If `knowledge_search` appears, explain that it is used for Java/backend/八股 technical context. Never quote the rendered prompt.

## Validation
```powershell
python skills/chat-routing-tool/scripts/plan_turn.py --self-test
python skills/chat-routing-tool/scripts/plan_turn.py --help
docker compose exec api python /app/skills/chat-routing-tool/scripts/plan_turn.py --message "你好"
docker compose exec api python /app/skills/chat-routing-tool/scripts/plan_turn.py --message "帮我找北京 Java 后端实习并结合简历分析"
docker compose exec api python /app/skills/chat-routing-tool/scripts/plan_turn.py --message "帮我搜一下美团开发岗"
docker compose exec api pytest tests/scheduled_tasks -q
```
