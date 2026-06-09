# 青程 AI 后端 Agent 学习路线

更新时间：2026-06-09

这份路线只覆盖后端 Agent 相关知识。目标是让中文母语学习者按一条不重复的路径学明白：用户一句话如何进入后端、如何被路由、如何调用工具、如何调用模型、如何写入记忆、如何被 Telegram 和定时任务复用，以及这些能力如何被测试和评测证明。

## 0. 怎么用这份路线

先按“主线 -> 支线 -> 底座 -> 验证”的顺序读：

1. 主线：AI 助手一轮聊天。
2. 支线：工具、RAG、记忆、定时任务、Telegram、面试、简历、通知。
3. 底座：Runtime、Provider、Prompt、Trace。
4. 验证：单元测试、golden cases、离线 eval、skills 脚本。

不要从私有函数 `_xxx` 开始读。先找 controller 或 service 的入口，再看 dataclass/schema，最后看私有辅助函数。

## 1. 覆盖矩阵

| 学习块 | 必读文件 | 学会什么 | 不重复边界 |
| --- | --- | --- | --- |
| Chat 主链路 | `backend/app/controllers/chat_controller.py`, `backend/app/services/chat_service.py` | 一轮聊天如何完成 | 不重复讲具体工具内部 |
| 路由规划 | `backend/app/agents/chat/complexity.py`, `backend/app/agents/supervisor.py`, `backend/app/prompts/templates/chat/supervisor.yaml` | intent、steps、tools 怎么来 | 不重复讲模型调用底座 |
| 工具适配 | `backend/app/services/chat_tool_service.py` | service 结果如何变成 tool_context | 不重复讲 service 业务细节 |
| RAG 知识库 | `backend/app/services/knowledge_rag_service.py`, `backend/app/services/citation_protocol.py`, `backend/app/tools/retrievers/` | 八股知识如何检索和引用 | 不重复讲岗位搜索 |
| 五层记忆 | `backend/app/services/ai_assistant_file_memory.py`, `backend/app/services/dream_memory_service.py`, `backend/app/services/assistant_memory_command_service.py` | session、history、USER、SOUL、MEMORY、Dream | 不重复讲普通数据库会话 |
| 定时任务 | `backend/app/services/scheduled_task_parser.py`, `backend/app/services/scheduled_task_service.py`, `backend/app/tasks/telegram_tasks.py` | 自然语言任务如何解析和执行 | 不重复讲 Telegram 绑定 |
| Telegram | `backend/app/services/telegram_bridge_service.py`, `backend/app/services/telegram_client.py`, `backend/app/services/telegram_offset_store.py` | 手机消息如何复用 AI 助手 | 不重复讲 ChatService 内部 |
| 面试 Agent | `backend/app/services/interview_service.py`, `backend/app/agents/interview/` | 面试状态机如何追问、评分、总结 | 不读取 AI 助手长期记忆 |
| 简历 Agent | `backend/app/agents/resume/`, `backend/app/services/resume_service.py` | 简历解析和评分如何由 Agent/Prompt 支撑 | 不重复讲岗位推荐 |
| 通知 Agent | `backend/app/agents/notification/decider.py`, `backend/app/services/proactive_notification_service.py` | 主动通知如何判断 send/skip | 不重复讲 Telegram 发送 |
| Runtime | `backend/app/agents/runtime/` | AgentContext、AgentRunner、生命周期 | 不重复讲具体业务 |
| Provider | `backend/app/core/providers/` | 模型 provider、mock、fallback | 不重复讲 Prompt 模板 |
| Prompt | `backend/app/prompts/registry.py`, `backend/app/prompts/templates/` | YAML Prompt 如何加载和校验 | 不重复讲工具结果 |
| Skills | `skills/*-tool/` | 开发/调试工具脚本怎么用 | 只列后端相关工具 |
| Evals | `backend/tests/agent_eval/`, `backend/evals/` | Agent 行为如何验收 | 不重复讲业务实现 |

## 2. 主线：AI 助手一轮聊天

重点文件：

- `backend/app/controllers/chat_controller.py`
- `backend/app/services/chat_service.py`
- `backend/app/services/chat_tool_service.py`
- `backend/app/agents/chat/assistant.py`

阅读顺序：

1. `chat_controller.py`：HTTP SSE 请求进入后端。
2. `ChatService.stream_events`：创建会话、构造 request id、拦截 slash command。
3. `ChatComplexityClassifier`：判断简单回答还是复杂任务。
4. `SupervisorAgent`：复杂任务生成 `intent`、`steps`、`tools`。
5. `ChatToolExecutor`：把简历、岗位、投递、知识库 service 结果包装成 `tool_context`。
6. `ChatAssistantAgent` + `AgentRunner`：调用模型并流式输出。
7. `_remember_turn`：把对话归档到 AI 助手文件记忆。

一句话理解：

> `ChatService` 是主编排层；它不自己做所有业务，而是把路由、工具、模型、记忆、持久化串成一轮可追踪的回合。

## 3. 路由规划：复杂度分类 + Supervisor

重点文件：

- `backend/app/agents/chat/complexity.py`
- `backend/app/agents/supervisor.py`
- `backend/app/prompts/templates/chat/supervisor.yaml`
- `backend/tests/agent_eval/test_chat_agent_intent.py`
- `backend/tests/agent_eval/test_chat_agent_tool_calls.py`

关键概念：

- `simple_answer`：无需工具的短回答。
- `agentic_task`：需要项目工具的复杂任务。
- `intent`：用户这一轮想完成什么。
- `steps`：回答前应该做哪些推理或操作。
- `tools`：后端允许这一轮调用哪些能力。

学习目标：

- 能解释为什么“找北京 Java 后端实习”会走 `job_search`。
- 能解释为什么“讲一下 JVM 内存模型”会走 `knowledge_search`。
- 能解释为什么模型不能自由写库，而是只能拿 allowlist 工具结果。

## 4. 工具适配层：从业务 service 到 tool_context

重点文件：

- `backend/app/services/chat_tool_service.py`
- `backend/app/services/resume_service.py`
- `backend/app/services/job_service.py`
- `backend/app/services/application_service.py`
- `backend/app/services/knowledge_rag_service.py`

工具边界：

- `resume_profile`：默认简历状态、评分、风险、技能；不返回完整简历原文。
- `job_search`：岗位检索、去重、推荐分、匹配技能、解释；不自动投递。
- `application_list`：保存岗位和投递状态；不调用外部平台提交。
- `knowledge_search`：八股知识库检索和引用；不暴露 raw prompt、向量库内部 id。

学习目标：

- 能说清楚 `ChatToolExecutor` 为什么放在 service 层，而不是 agent 层。
- 能说清楚 `tool_context` 是“给模型看的结构化事实”，不是数据库模型。

## 5. RAG 知识库链路

重点文件：

- `backend/app/services/knowledge_rag_service.py`
- `backend/app/services/citation_protocol.py`
- `backend/app/tools/retrievers/qdrant_retriever.py`
- `backend/app/tools/embeddings/provider.py`
- `backend/app/tools/embeddings/dashscope_adapter.py`
- `backend/app/tools/embeddings/fastembed_adapter.py`
- `backend/app/services/knowledge_ingestion.py`
- `backend/app/services/knowledge_markdown.py`
- `backend/evals/rag/eval_knowledge_rag.py`
- `backend/tests/agent_eval/test_rag_grounding.py`

阅读顺序：

1. `knowledge_ingestion.py`：知识如何切块、入库、生成 embedding。
2. `backend/app/tools/embeddings/provider.py`：如何选择 embedding provider。
3. `qdrant_retriever.py`：如何从向量库召回候选。
4. `knowledge_rag_service.py`：如何组合检索、重排、fallback、citation。
5. `citation_protocol.py`：回答如何携带可展示的引用信息。
6. RAG eval：如何证明回答有 grounding，不是空编。

学习目标：

- 能解释 chunk、embedding、retrieval、citation 的关系。
- 能解释 RAG 结果为什么进入 `knowledge_search`，而不是直接让模型访问向量库。

## 6. 五层记忆与 Dream

重点文件：

- `backend/app/services/ai_assistant_file_memory.py`
- `backend/app/services/dream_memory_service.py`
- `backend/app/services/assistant_memory_command_service.py`
- `backend/app/services/assistant_memory_markdown_service.py`
- `backend/tests/memory/test_ai_assistant_file_memory.py`
- `backend/tests/memory/test_dream_memory_service.py`
- `docs/architecture/ai-memory-system.md`

五层结构：

- `session.messages`：数据库里的当前短期会话。
- `sessions/<session_id>.jsonl`：当前会话原始归档。
- `memory/history.jsonl`：Consolidator 写入的压缩摘要。
- `USER.md`：用户档案。
- `SOUL.md`：沟通风格。
- `memory/MEMORY.md`：项目知识和长期决策。

命令入口：

- `/dream`：立即整理长期记忆。
- `/dream-log`：看最近 Dream diff 和分析。
- `/dream-log <sha>`：看指定 Dream。
- `/dream-restore`：列出可回滚提交。
- `/dream-restore <sha>`：回滚某次 Dream 变更。

学习目标：

- 能解释为什么压缩写 `history.jsonl`，而不是直接改 `USER.md`。
- 能解释 Dream 为什么要 commit 到用户 runtime Git，而不是项目 Git。
- 能解释为什么面试助手不读取 AI 助手长期记忆。

## 7. 定时任务 Agent 能力

重点文件：

- `backend/app/services/scheduled_task_parser.py`
- `backend/app/services/scheduled_task_service.py`
- `backend/app/repositories/scheduled_task_repository.py`
- `backend/app/tasks/telegram_tasks.py`
- `backend/tests/scheduled_tasks/`
- `skills/scheduled-task-tool/SKILL.md`

阅读顺序：

1. parser：自然语言如何变成 `once/interval/cron/list/pause/resume/cancel`。
2. service：任务如何创建、暂停、恢复、取消、执行。
3. worker：如何扫描到期任务。
4. ChatService 复用：执行任务时如何避免递归创建新任务。

学习目标：

- 能解释“明天早上提醒我投递简历”如何变成数据库任务。
- 能解释定时任务为什么是应用级任务，不是系统 cron。

## 8. Telegram 通道

重点文件：

- `backend/app/services/telegram_bridge_service.py`
- `backend/app/services/telegram_client.py`
- `backend/app/services/telegram_offset_store.py`
- `backend/app/repositories/notification_repository.py`
- `backend/app/tasks/telegram_tasks.py`
- `backend/tests/telegram/`
- `skills/telegram-notification-tool/SKILL.md`

必须掌握：

- `/bind CODE`：绑定 Telegram 账号。
- `/new`：新开 Telegram 会话。
- `/sessions`：查看最近会话。
- `/use <id-prefix>`：切换会话。
- `/dream`、`/dream-log`、`/dream-restore`：复用 AI 助手记忆命令。

学习目标：

- 能解释 Telegram 普通消息如何复用 `ChatService`。
- 能解释 Telegram 为什么不是新的独立 Agent。
- 能解释 offset store 为什么用于避免重复消费更新。

## 9. 面试 Agent 状态机

重点文件：

- `backend/app/services/interview_service.py`
- `backend/app/agents/interview/models.py`
- `backend/app/agents/interview/runtime.py`
- `backend/app/agents/interview/planner.py`
- `backend/app/agents/interview/evaluator.py`
- `backend/app/agents/interview/feedback.py`
- `backend/app/agents/interview/tools.py`
- `backend/app/tools/interview/rule_engine.py`
- `backend/tests/interview/`
- `backend/tests/agent_eval/test_interview_question_plan.py`
- `backend/tests/agent_eval/test_interview_followup_policy.py`
- `skills/interview-state-tool/SKILL.md`

阅读顺序：

1. `models.py`：先理解面试状态的数据结构。
2. `runtime.py`：看状态如何初始化、压缩、推进。
3. `planner.py`：看问题计划如何生成。
4. `evaluator.py` 和 `rule_engine.py`：看回答如何评分。
5. `feedback.py`：看流式反馈如何生成。
6. `interview_service.py`：看一轮面试如何落库和输出。

学习目标：

- 能解释 `interview_sessions.report.agent_state` 保存了什么。
- 能解释多轮追问如何依赖状态，而不是只依赖最近一句话。
- 能解释面试助手为什么只维护当前面试场次。

## 10. 简历 Agent 与简历业务

重点文件：

- `backend/app/agents/resume/parser.py`
- `backend/app/agents/resume/scorer.py`
- `backend/app/prompts/templates/resume/parse.yaml`
- `backend/app/prompts/templates/resume/score.yaml`
- `backend/app/services/resume_service.py`
- `backend/app/tools/parsers/pdf_parser.py`
- `backend/tests/agent_eval/test_resume_score_rubric.py`
- `skills/resume-profile-tool/SKILL.md`

学习目标：

- 能解释简历文本如何从文件解析出来。
- 能解释结构化解析和评分为什么拆成两个 Agent/Prompt。
- 能解释评分结果如何被 `resume_profile` 工具复用。

## 11. 通知 Agent 与主动推送

重点文件：

- `backend/app/agents/notification/decider.py`
- `backend/app/prompts/templates/notification/proactive_decision.yaml`
- `backend/app/services/proactive_notification_service.py`
- `backend/app/repositories/notification_repository.py`
- `backend/tests/telegram/test_proactive_notifications.py`

学习目标：

- 能解释候选通知如何经过规则门控和 LLM send/skip 判断。
- 能解释主动通知为什么需要审计记录。
- 能解释通知 Agent 只做决策，不直接发送消息。

## 12. Agent Runtime 底座

重点文件：

- `backend/app/agents/runtime/base.py`
- `backend/app/agents/runtime/runner.py`
- `backend/app/agents/runtime/lifecycle.py`
- `backend/tests/agents/test_agent_runtime.py`
- `backend/tests/agents/test_agent_lifecycle.py`

关键概念：

- `AgentContext`：一次 Agent 调用的上下文，包含 provider、request id、assistant type。
- `AgentRunner.run`：一次性生成完整结果。
- `AgentRunner.stream`：流式生成增量结果。
- `AgentLifecycleRecorder`：记录 BeforeTurn、PromptRender、Reasoner、AfterTurn 等阶段。

学习目标：

- 能解释为什么所有 Agent 调模型都走 Runtime，而不是各写各的 provider 调用。
- 能解释 lifecycle metadata 如何帮助调试和评测。

## 13. Provider 与模型 fallback

重点文件：

- `backend/app/core/providers/base.py`
- `backend/app/core/providers/factory.py`
- `backend/app/core/providers/claude_provider.py`
- `backend/app/core/providers/mock_provider.py`
- `backend/app/core/settings.py`
- `backend/tests/provider/`
- `skills/llm-provider-tool/SKILL.md`

学习目标：

- 能解释 provider factory 如何根据配置选择模型。
- 能解释 mock provider 为什么用于测试。
- 能解释模型失败后为什么要有 fallback，而不是直接让请求崩掉。

## 14. Prompt 工程化

重点文件：

- `backend/app/prompts/registry.py`
- `backend/app/prompts/templates/chat/simple_answer.yaml`
- `backend/app/prompts/templates/chat/supervisor.yaml`
- `backend/app/prompts/templates/interview/feedback.yaml`
- `backend/app/prompts/templates/interview/summary.yaml`
- `backend/tests/prompts/test_prompt_registry.py`

必须掌握：

- Prompt 模板固定包含 `id/version/system/user/variables/output_contract/safety_notes`。
- `StrictUndefined` 让缺变量直接失败，避免静默生成坏 prompt。
- Prompt 是 Agent 行为的一部分，必须可版本化、可测试、可替换。

## 15. Trace、输出格式与安全边界

重点文件：

- `backend/app/services/trace.py`
- `backend/app/services/chat_output_format.py`
- `backend/app/services/streaming.py`
- `backend/app/services/citation_protocol.py`
- `docs/security/llm-risk-boundaries.md`
- `backend/tests/chat/test_chat_output_format.py`
- `backend/tests/knowledge/test_citation_protocol.py`

学习目标：

- 能解释 metadata 里为什么有 `agent_chain`、`tool_calls_summary`、`safety_boundary`。
- 能解释为什么要统一清洗模型输出格式。
- 能解释知识库引用和安全边界如何进入最终响应元数据。

## 16. Skills：后端延伸工具

这里的 skills 是给开发者或 Agent 使用的工具说明和脚本，不是业务接口本身。本路线只列后端相关工具。

| Skill | 入口脚本 | 学会什么 |
| --- | --- | --- |
| `chat-routing-tool` | `skills/chat-routing-tool/scripts/plan_turn.py` | 检查一条输入会被规划成什么 intent/tools |
| `assistant-memory-tool` | `inspect_memory.py`, `export_memory_md.py` | 查看 AI 助手文件记忆 |
| `job-search-tool` | `discover_jobs.py` | 调试岗位发现和推荐 |
| `knowledge-search-tool` | `search_knowledge.py` | 调试 RAG 检索结果 |
| `resume-profile-tool` | `inspect_resume_profile.py` | 查看默认简历画像 |
| `application-list-tool` | `list_applications.py` | 查看保存/投递状态 |
| `interview-state-tool` | `inspect_interview_state.py` | 查看面试状态机 |
| `scheduled-task-tool` | 无脚本，以说明为主 | 理解定时任务语义 |
| `telegram-notification-tool` | 无脚本，以说明为主 | 理解 Telegram/通知边界 |
| `llm-provider-tool` | `check_provider.py` | 检查当前模型 provider |
| `agent-evaluation-tool` | `run_agent_eval.py` | 运行 Agent 评测 |
| `backend-service-tool` | `list_routes.py` | 查看后端路由和 service 入口 |
| `runtime-ops-tool` | 无脚本，以说明为主 | 理解运行维护命令 |

学习目标：

- 能把 skill 看成“可复用操作手册 + 轻量脚本”。
- 能解释脚本返回结构化事实，最终自然语言回答仍由 Agent 组织。

## 17. 测试与评测

重点文件：

- `backend/tests/agent_eval/`
- `backend/tests/agent_eval/golden_cases/*.jsonl`
- `backend/evals/agent/run_agent_eval.py`
- `backend/evals/rag/eval_knowledge_rag.py`
- `backend/tests/chat/`
- `backend/tests/memory/`
- `backend/tests/scheduled_tasks/`
- `backend/tests/telegram/`
- `backend/tests/interview/`

常用命令：

```powershell
python -m compileall -q backend/app
python -m pytest backend/tests/agent_eval -q
python -m pytest backend/tests/chat backend/tests/memory backend/tests/scheduled_tasks backend/tests/telegram backend/tests/interview -q
python backend/evals/agent/run_agent_eval.py
python backend/evals/rag/eval_knowledge_rag.py
```

学习目标：

- 能解释 golden cases 验什么。
- 能解释单元测试、集成测试、离线 eval 的区别。
- 能解释为什么 Agent 能力不能只靠“接口返回 200”证明。

## 18. 最短学习路径

如果只想快速讲明白项目，按这个顺序读：

1. `docs/architecture/project-map.md`
2. `backend/app/services/chat_service.py`
3. `backend/app/agents/chat/complexity.py`
4. `backend/app/agents/supervisor.py`
5. `backend/app/services/chat_tool_service.py`
6. `backend/app/services/knowledge_rag_service.py`
7. `backend/app/services/ai_assistant_file_memory.py`
8. `backend/app/services/dream_memory_service.py`
9. `backend/app/services/scheduled_task_service.py`
10. `backend/app/services/telegram_bridge_service.py`
11. `backend/app/services/interview_service.py`
12. `backend/app/agents/runtime/runner.py`
13. `backend/app/core/providers/factory.py`
14. `backend/tests/agent_eval/`

读完这条最短路径，你应该能讲清楚：

- 后端有哪些 Agent。
- 每个 Agent 的边界是什么。
- Agent 如何调用工具。
- 工具如何复用 service。
- 记忆如何压缩、沉淀、回滚。
- RAG 如何提供可引用知识。
- 定时任务和 Telegram 如何复用 AI 助手。
- 面试助手为什么是独立状态机。
- 如何用测试和 eval 证明这些能力存在。
