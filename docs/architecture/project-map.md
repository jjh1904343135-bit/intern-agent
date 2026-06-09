# 青程 AI 项目代码地图

更新时间：2026-06-04

这份文档用于从零阅读当前项目。它不按“页面数量”组织，而按真实工程链路组织：入口层、Agent 层、Prompt 层、记忆层、工具层、前端层。

## 1. 运行入口

- `docker-compose.yml`：本地运行总入口，管理 api、worker、frontend、nginx、postgres、redis、qdrant。
- `backend/app/main.py`：FastAPI 应用入口，注册路由、启动生命周期任务。
- `backend/app/core/settings.py`：统一读取 `.env`，包含 LLM、Embedding、Qdrant、Telegram、文件化记忆目录等配置。
- `backend/app/core/database.py`：PostgreSQL session 管理。

## 2. HTTP 入口层

- `backend/app/controllers/auth_controller.py`：注册、登录、Token。
- `backend/app/controllers/resume_controller.py`：简历上传、解析状态、评分报告。
- `backend/app/controllers/job_controller.py`：统一岗位搜索、详情、推荐。
- `backend/app/controllers/application_controller.py`：保存岗位、手动投递状态流。
- `backend/app/controllers/chat_controller.py`：AI 助手 SSE 对话。
- `backend/app/controllers/interview_controller.py`：模拟面试开始、回答、流式反馈、报告。
- `backend/app/controllers/telegram_controller.py`：Telegram 一次性绑定码。
- `backend/app/controllers/scheduled_task_controller.py`：AI 助手定时任务列表、状态更新、执行记录和任务收件箱。

Controller 只处理请求/响应和鉴权，业务编排放在 service。

## 3. Service 业务层

- `backend/app/services/chat_service.py`：AI 助手主编排。当前流程是复杂度判断 -> 简单直答或 Agent Pipeline -> 工具调用 -> 流式生成 -> 文件化记忆归档。
- `backend/app/services/interview_service.py`：模拟面试编排。只维护当前面试 session 的短期状态，不再写复杂长期面试记忆。
- `backend/app/services/resume_service.py`：文件上传、文本提取、结构化解析、Rubric 评分。
- `backend/app/services/job_service.py`：岗位搜索、推荐评分、解释、去重、RAG payload。
- `backend/app/services/knowledge_rag_service.py`：AI 助手八股知识库 Hybrid RAG。
- `backend/app/services/ai_assistant_file_memory.py`：AI 助手文件化长期记忆，实现 `sessions/*.jsonl`、`history.jsonl`、`USER.md`、`MEMORY.md`、`SOUL.md`。
- `backend/app/services/telegram_bridge_service.py`：Telegram 入站消息复用 AI 助手能力。
- `backend/app/services/proactive_notification_service.py`：主动推送候选和 send/skip 决策。
- `backend/app/services/scheduled_task_parser.py`：定时任务自然语言识别，规则优先解析一次性、interval、cron、工作日等表达。
- `backend/app/services/scheduled_task_service.py`：任务创建、列出、暂停、取消、到期执行、收件箱写入和 Telegram 回传。

## 4. Agent 层

- `backend/app/agents/chat/complexity.py`：简单问题和复杂任务分类。简单问题不调工具，复杂任务进入 Agent Pipeline。
- `backend/app/agents/supervisor.py`：AI 助手复杂任务规划，决定 intent、steps、tools。
- `backend/app/agents/runtime/`：Agent 生命周期和流式执行抽象。
- `backend/app/agents/interview/`：面试 Agent 状态机，包括岗位画像、候选人画像、问题计划、回答信号、评分、难度、追问和总结。

当前设计边界：AI 助手是求职 Agent 总入口；面试助手只做模拟面试，不读取 AI 助手会话和长期记忆。

## 5. Prompt 层

Prompt 不再散落在 service 中，统一放在：

```text
backend/app/prompts/templates/
  chat/
  resume/
  interview/
  notification/
```

核心加载器：`backend/app/prompts/registry.py`。

模板格式是 YAML + Jinja2，字段固定包含：

- `id`
- `version`
- `system`
- `user`
- `variables`
- `output_contract`
- `safety_notes`

这样做的原因：Prompt 是 Agent 行为的一部分，必须可版本化、可测试、可替换，而不是隐藏在 Python 字符串里。

## 6. 记忆层

### AI 助手

AI 助手使用文件化长期记忆，运行目录：

```text
runtime/ai_assistant_memory/users/<user_id>/
  sessions/<session_id>.jsonl
  memory/history.jsonl
  USER.md
  MEMORY.md
  SOUL.md
```

- `chat_sessions` 仍是业务会话权威来源。
- 文件记忆是 Agent 可读上下文层。
- 会话过长时 soft consolidation 只追加摘要到 `history.jsonl`，不覆盖原始 session JSONL。
- Dream 第一版只做本地最小编辑，不做 git commit，不暴露内部推理。

### 面试助手

面试助手只保留当前场次短期记忆：

```text
interview_sessions.report.agent_state
```

它保存 `job_profile`、`candidate_profile`、`question_plan`、`asked_questions`、`evaluation_state`、`difficulty`、`remaining_focus`。当当前场次过长时，只把早期问答压缩成 `session_summary`，仍放在当前 session 内。

## 7. 工具层

- `backend/app/tools/job_discovery/`：岗位源 adapter、query expansion、taxonomy、去重聚合。
- `backend/app/tools/retrievers/`：Qdrant 和关键词检索工具。
- `skills/`：项目专用能力说明和轻量脚本，供 Agent 或开发者快速调用。

工具调用原则：模型不能自由写库；所有工具由服务端 allowlist 和 service 控制。

## 8. 前端层

- `frontend/src/app/`：Next.js App Router 页面。
- `frontend/src/components/`：产品组件、聊天组件、岗位卡、简历评分卡、Telegram 绑定卡。
- `frontend/src/lib/api.ts`：统一 API 请求封装。
- `frontend/src/lib/auth.ts`：Token 存取。

`frontend/src/components/telegram-bind-card.tsx` 在 `/chat` 会话侧栏展示 Telegram 绑定入口。Telegram 绑定后复用 AI 助手，不接入面试助手。

定时任务入口同样在 `/chat`：`frontend/src/components/scheduled-task-panel.tsx` 展示最近任务和任务收件箱。用户主要通过自然语言创建任务，侧栏只提供刷新、暂停、恢复、取消和标记已读。

## 9. 推荐阅读顺序

1. `backend/app/services/chat_service.py`
2. `backend/app/agents/chat/complexity.py`
3. `backend/app/prompts/registry.py`
4. `backend/app/prompts/templates/chat/supervisor.yaml`
5. `backend/app/services/ai_assistant_file_memory.py`
6. `backend/app/services/interview_service.py`
7. `backend/app/agents/interview/`
8. `frontend/src/app/chat/page.tsx`
9. `frontend/src/components/telegram-bind-card.tsx`
10. `frontend/src/components/scheduled-task-panel.tsx`
11. `skills/chat-routing-tool/SKILL.md`
12. `skills/assistant-memory-tool/SKILL.md`
13. `skills/telegram-notification-tool/SKILL.md`
14. `skills/scheduled-task-tool/SKILL.md`
