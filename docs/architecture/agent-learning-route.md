# 青程 AI Agent 学习路线

更新时间：2026-06-09

这份文档面向中文母语学习者，用来从零理解项目里的 Agent 代码。它不按页面或功能堆文件名，而按“一句话进系统后发生什么”来组织阅读顺序。

## 0. 先建立总览

先读：

- `README.md`
- `CONTRIBUTING.md`
- `docs/architecture/project-map.md`
- `docs/architecture/ai-memory-system.md`
- `docs/project-standards-review.md`

必须先知道的边界：

- AI 助手是求职主入口，负责聊天、岗位、简历、投递、RAG、记忆和定时任务。
- 面试助手是独立的模拟面试状态机，不读取 AI 助手的长期记忆。
- Telegram 是 AI 助手的外部通道，不是另一个独立助手。
- Agent 不直接写数据库，所有真实业务动作都通过 service 和 repository 完成。

## 1. ChatService：一次聊天请求的主链路

重点文件：

- `backend/app/controllers/chat_controller.py`
- `backend/app/services/chat_service.py`
- `backend/app/services/chat_tool_service.py`
- `backend/app/agents/chat/assistant.py`
- `backend/app/agents/runtime/`

阅读问题：

1. Controller 如何把 SSE 请求交给 `ChatService.stream_events`。
2. `stream_events` 如何生成 `request_id`、`agent_run_id` 和生命周期记录。
3. `/dream` 这类 slash command 为什么先于定时任务和普通 LLM 对话被拦截。
4. 简单问题和复杂任务如何分流。
5. `ChatToolExecutor` 如何把 service 结果包装成 Agent 可读的 `tool_context`。
6. `AgentRunner.stream` 如何把模型输出变成 `start -> delta -> end`。
7. 最终回答如何落库，并写入 AI 助手文件记忆。

一句话理解：

> `ChatService` 是聊天主编排层；它负责把用户输入、业务工具、文件记忆、模型调用和流式输出串起来。

## 2. 路由与规划：复杂度分类 + Supervisor

重点文件：

- `backend/app/agents/chat/complexity.py`
- `backend/app/agents/supervisor.py`
- `backend/app/prompts/templates/chat/supervisor.yaml`
- `backend/tests/agent_eval/test_chat_agent_intent.py`
- `backend/tests/agent_eval/test_chat_agent_tool_calls.py`

必须掌握：

- `simple_answer`：问候、短问题、无需工具的直接回答。
- `agentic_task`：岗位、简历、投递、面试、技术八股等需要项目工具的任务。
- `SupervisorAgent` 负责生成 `intent`、`steps`、`tools`。
- 工具选择是 allowlist，不让模型自由操作系统。

命名提示：

- `intent` 表示“这句话想做什么”。
- `tools` 表示“这轮允许调用哪些后端能力”。
- `tool_context` 表示“工具执行后给模型看的结构化事实”。

## 3. 工具层：模型能用哪些真实能力

重点文件：

- `backend/app/services/chat_tool_service.py`
- `backend/app/services/resume_service.py`
- `backend/app/services/job_service.py`
- `backend/app/services/application_service.py`
- `backend/app/services/knowledge_rag_service.py`
- `skills/*-tool/scripts/*.py`

工具边界：

- `resume_profile`：读取默认简历状态、评分、风险和技能，不返回完整简历原文。
- `job_search`：岗位检索、去重、推荐分、匹配技能和解释，不自动投递。
- `application_list`：读取保存和投递状态，不对外部平台提交。
- `knowledge_search`：检索八股知识库，不暴露 raw prompt 或底层向量库细节。

一句话理解：

> 工具层复用已有 service，不复制业务逻辑；Agent 只拿结构化结果，再组织自然语言回答。

## 4. PromptRegistry：Prompt 工程化

重点文件：

- `backend/app/prompts/registry.py`
- `backend/app/prompts/templates/chat/simple_answer.yaml`
- `backend/app/prompts/templates/chat/supervisor.yaml`
- `backend/tests/prompts/test_prompt_registry.py`

必须掌握：

- Prompt 模板固定包含 `id/version/system/user/variables/output_contract/safety_notes`。
- `StrictUndefined` 会让缺失变量直接报错，避免静默生成坏 prompt。
- Prompt 是 Agent 行为的一部分，必须可版本化、可测试、可替换。

## 5. 五层记忆系统

重点文件：

- `backend/app/services/ai_assistant_file_memory.py`
- `backend/app/services/dream_memory_service.py`
- `backend/app/services/assistant_memory_command_service.py`
- `backend/tests/memory/test_ai_assistant_file_memory.py`
- `backend/tests/memory/test_dream_memory_service.py`
- `docs/architecture/ai-memory-system.md`

记忆层级：

- `session.messages`：数据库里的当前短期会话。
- `sessions/<session_id>.jsonl`：当前会话原始归档。
- `memory/history.jsonl`：Consolidator 写入的压缩摘要。
- `USER.md`：用户档案。
- `SOUL.md`：沟通风格。
- `memory/MEMORY.md`：项目知识和长期决策。

一句话理解：

> 压缩只把旧消息提炼成摘要，不删除原始会话；Dream 再把摘要沉淀进长期 Markdown 文件。

## 6. 定时任务与 Telegram

重点文件：

- `backend/app/services/scheduled_task_parser.py`
- `backend/app/services/scheduled_task_service.py`
- `backend/app/tasks/telegram_tasks.py`
- `backend/app/services/telegram_bridge_service.py`
- `backend/tests/scheduled_tasks/`
- `backend/tests/telegram/`

必须掌握：

- 定时任务是应用级任务，不是系统 cron。
- 自然语言先被解析成 `once/interval/cron/list/pause/resume/cancel`。
- worker 扫描到期任务，执行时复用 `ChatService`。
- Telegram 普通消息复用 AI 助手，`/new` 只切换手机端当前会话。

## 7. 面试助手状态机

重点文件：

- `backend/app/services/interview_service.py`
- `backend/app/agents/interview/runtime.py`
- `backend/app/agents/interview/planner.py`
- `backend/app/agents/interview/evaluator.py`
- `backend/app/agents/interview/models.py`
- `backend/tests/interview/`

必须掌握：

- 面试状态存在 `interview_sessions.report.agent_state`。
- 初始状态由岗位画像和候选人画像生成问题计划。
- 每轮回答会更新信号、评分、难度、追问策略和剩余考察点。
- 面试助手只维护当前面试场次，不写 AI 助手长期记忆。

## 8. 命名与注释规则

代码命名保持英文，原因是 Python 生态、测试、搜索和第三方库都默认英文；中文主要用于文档、模块说明、关键注释和术语表。

推荐命名：

- 用业务名词：`ChatService`、`JobSearchCandidate`、`DreamMemoryService`。
- 用动作动词：`stream_events`、`discover_jobs`、`soft_consolidate`。
- 用边界词：`controller` 处理 HTTP，`service` 编排业务，`repository` 访问数据库，`agent` 负责规划/生成/评估。
- 少用空泛词：`manager`、`helper`、`processor`、`data`、`info`。如果用了，旁边必须能看出具体业务含义。

推荐注释：

- 文件顶部说明“这个文件属于哪一层、负责什么、不负责什么”。
- 大函数前说明流程，而不是逐行翻译代码。
- 复杂判断旁说明原因，例如安全边界、业务取舍、压缩阈值。
- 不写“给变量赋值”这类无信息注释。

中文学习者阅读技巧：

- 先看文件顶部说明，再看 dataclass/schema，再看公开方法。
- 遇到英文名，先按“业务名词 + 动作”拆开理解。
- 不要从私有函数 `_xxx` 开始读；先找 controller 或 service 的入口。
- 看测试时优先读断言，断言通常比实现更直接说明行为。

## 9. 验收与评测

常用命令：

```powershell
python -m compileall -q backend/app
python -m pytest backend/tests/chat backend/tests/memory backend/tests/scheduled_tasks backend/tests/telegram -q
python -m pytest backend/tests/agent_eval -q
```

一句话理解：

> Agent 能力不是口头设计，必须用 golden cases、单元测试和端到端流式测试证明。
