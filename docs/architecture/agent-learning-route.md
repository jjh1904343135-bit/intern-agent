# 青程 AI Agent 学习路线

更新时间：2026-06-06

这份路线只围绕面试时能讲清楚的 Agent 能力组织，不按页面、不按历史 Day 组织。学习目标是能把“用户一句话进入系统后，如何被路由、调用工具、生成回答、写入记忆、触发任务或 Telegram 回复”完整讲出来。

## 0. 先建立总览

目标：知道项目有哪些 Agent 能力，以及每个能力的边界。

重点文件：

- `docs/architecture/project-map.md`
- `docs/project-review-status.md`
- `skills/*/SKILL.md`

必须掌握：

- AI 助手是主入口，负责求职问答、岗位、简历、投递、RAG、定时任务。
- 面试助手是独立状态机，只服务模拟面试，不读取 AI 助手长期记忆。
- Telegram 是 AI 助手的外部通道，不是新的独立助手。
- Skills 是工具说明书，脚本只返回结构化事实，最终回答由大模型整理。

## 1. ChatService：Agent 主链路

目标：看懂一次 `/chat` 请求如何完成。

重点文件：

- `backend/app/controllers/chat_controller.py`
- `backend/app/services/chat_service.py`
- `backend/app/agents/runtime/lifecycle.py`
- `backend/app/agents/chat/assistant.py`

阅读顺序：

1. Controller 如何把 SSE 请求交给 `ChatService.stream_events`。
2. `stream_events` 如何生成 `request_id`、`agent_run_id` 和生命周期记录。
3. 定时任务为什么先于普通回答处理。
4. 简单问题与复杂任务如何分流。
5. 工具结果如何进入 `tool_context`。
6. `AgentRunner.stream` 如何把模型输出变成 `start -> delta -> end/error`。
7. 最终回答如何落库并写入文件记忆。

面试表达：

> 我把 ChatService 设计成主编排层，模型不是直接访问数据库，而是由服务端先分类、再决定 allowlist 工具、再把工具事实注入 Prompt，最后统一流式输出和记忆归档。

## 2. 路由与规划：复杂度分类 + Supervisor

目标：知道用户问题为什么会走某个工具。

重点文件：

- `backend/app/agents/chat/complexity.py`
- `backend/app/agents/supervisor.py`
- `backend/app/prompts/templates/chat/supervisor.yaml`
- `skills/chat-routing-tool/scripts/plan_turn.py`

必须掌握：

- `simple_answer`：问候、短问题、无需工具的直接回答。
- `agentic_task`：岗位、简历、投递、面试、技术八股等需要项目工具的任务。
- `SupervisorAgent` 负责意图识别、步骤规划和工具选择。
- Java、后端、八股、Redis、MySQL 等问题会额外触发 `knowledge_search`。

面试表达：

> 这里不是让模型自由决定怎么操作系统，而是先用规则做稳定分流，再由 Supervisor 生成可审计的 intent、steps、tools，工具仍由服务端执行。

## 3. PromptRegistry：Prompt 工程化

目标：理解 Prompt 为什么从 Python 字符串拆成 YAML 模板。

重点文件：

- `backend/app/prompts/registry.py`
- `backend/app/prompts/templates/chat/simple_answer.yaml`
- `backend/app/prompts/templates/chat/supervisor.yaml`
- `backend/tests/prompts/test_prompt_registry.py`

必须掌握：

- Prompt 模板固定有 `id/version/system/user/variables/output_contract/safety_notes`。
- `StrictUndefined` 保证变量缺失时直接失败，避免隐式空字符串。
- Prompt 是 Agent 行为的一部分，需要可版本化、可测试、可替换。

## 4. 工具调用：项目内真实能力

目标：知道 Agent 能调用哪些项目能力，以及为什么不能越界。

重点文件：

- `backend/app/services/chat_service.py` 的 `_run_tools`
- `backend/app/services/resume_service.py`
- `backend/app/services/job_service.py`
- `backend/app/services/application_service.py`
- `backend/app/services/knowledge_rag_service.py`
- `skills/*-tool/scripts/*.py`

工具边界：

- `resume_profile`：读取默认简历状态、评分、风险、技能，不返回完整简历原文。
- `job_search`：岗位检索、去重、推荐分、匹配技能，不自动投递。
- `application_list`：读取保存和投递状态，不对外部平台提交。
- `knowledge_search`：Hybrid RAG 检索八股知识，不暴露 Qdrant point id 和 raw prompt。

面试表达：

> 工具层复用已有 service，不复制业务逻辑。Agent 只拿结构化结果，回答阶段再组织自然语言。

## 5. 文件化长期记忆

目标：讲清楚这个项目里的“记忆”到底是什么。

重点文件：

- `backend/app/services/ai_assistant_file_memory.py`
- `backend/app/services/assistant_memory_markdown_service.py`
- `backend/tests/memory/test_ai_assistant_file_memory.py`
- `skills/assistant-memory-tool/SKILL.md`

必须掌握：

- PostgreSQL `chat_sessions` 是业务会话事实源。
- `runtime/ai_assistant_memory/users/<user_id>/` 是 Agent 可读上下文层。
- `sessions/<session_id>.jsonl` 记录当前会话归档。
- `memory/history.jsonl` 保存压缩摘要。
- `USER.md`、`MEMORY.md`、`SOUL.md` 提供类似 Claude memory 的可读上下文。
- 面试助手不读取这套 AI 助手记忆。

## 6. 定时任务 Agent 能力

目标：理解“提醒我/每天/每周/每隔多久”如何变成可执行任务。

重点文件：

- `backend/app/services/scheduled_task_parser.py`
- `backend/app/services/scheduled_task_service.py`
- `backend/app/repositories/scheduled_task_repository.py`
- `backend/app/tasks/telegram_tasks.py`
- `backend/app/controllers/scheduled_task_controller.py`
- `frontend/src/components/scheduled-task-panel.tsx`
- `skills/scheduled-task-tool/SKILL.md`

必须掌握：

- 定时任务是应用级任务，不是操作系统 cron。
- 自然语言先由 parser 识别成 `once/interval/cron/list/pause/resume/cancel`。
- 任务存入 PostgreSQL，worker 扫描到期任务。
- 执行时复用 `ChatService`，并跳过再次识别定时任务，避免递归创建任务。
- 结果写入任务收件箱；Telegram 创建的任务会回传到同一个 Telegram chat。

## 7. Telegram 通道

目标：讲清楚手机端为什么能复用网页 AI 助手会话。

重点文件：

- `backend/app/services/telegram_bridge_service.py`
- `backend/app/tasks/telegram_tasks.py`
- `backend/app/repositories/notification_repository.py`
- `backend/app/services/proactive_notification_service.py`
- `frontend/src/components/telegram-bind-card.tsx`
- `skills/telegram-notification-tool/SKILL.md`

必须掌握：

- Web 端生成一次性绑定码，Telegram 发送 `/bind CODE`。
- 数据库只保存绑定码 hash，不保存明文 code。
- Telegram account 有 sticky `chat_session_id`，普通消息会继续当前会话。
- `/new` 新开手机会话，`/sessions` 查看最近会话，`/use <id-prefix>` 切换。
- 主动推送走候选事件、规则门控、LLM send/skip、Telegram 发送、审计记录。

## 8. 面试 Agent 状态机

目标：理解多轮面试为什么能持续追问。

重点文件：

- `backend/app/services/interview_service.py`
- `backend/app/agents/interview/runtime.py`
- `backend/app/agents/interview/planner.py`
- `backend/app/agents/interview/evaluator.py`
- `backend/app/agents/interview/models.py`
- `frontend/src/app/interview/[id]/page.tsx`
- `skills/interview-state-tool/SKILL.md`

必须掌握：

- 面试状态存在 `interview_sessions.report.agent_state`。
- 初始状态由岗位画像和候选人画像生成问题计划。
- 每轮回答会抽取回答信号、更新评分、调整难度、选择追问策略。
- 长面试只在当前 session 内压缩，不写 AI 助手长期记忆。

## 9. 前端如何承接 Agent Metadata

目标：知道后端 Agent 输出如何变成用户能看到的界面。

重点文件：

- `frontend/src/app/chat/page.tsx`
- `frontend/src/components/chat-message-list.tsx`
- `frontend/src/components/agent-trace.tsx`
- `frontend/src/components/scheduled-task-panel.tsx`
- `frontend/src/components/telegram-bind-card.tsx`

必须掌握：

- 前端消费 SSE 的 `start/delta/end/error`。
- `metadata.tool_calls_summary`、`knowledge_references`、`suggested_actions` 变成轻量 UI。
- 前端不展示 raw prompt、完整推理链和敏感工具上下文。

## 10. 评测与验收

目标：知道如何证明 Agent 能力不是口头设计。

重点文件：

- `backend/tests/agent_eval/`
- `backend/evals/agent/run_agent_eval.py`
- `backend/evals/rag/eval_knowledge_rag.py`
- `backend/tests/scheduled_tasks/`
- `backend/tests/telegram/`

常用命令：

```powershell
python -m compileall -q backend\app
python -m pytest backend\tests\chat backend\tests\memory backend\tests\scheduled_tasks backend\tests\telegram -q
docker compose exec api pytest tests/agent_eval tests/knowledge tests/interview -q
```

面试表达：

> 我用 golden cases 和专项测试验证 Agent 行为，包括意图识别、工具选择、参数、RAG grounding、面试追问和定时任务解析，而不是只看接口能不能返回 200。
