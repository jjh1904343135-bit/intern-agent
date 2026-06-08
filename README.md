# 青程 AI

青程 AI（工程名 InternAgent）是一个面向实习与校招准备的 AI 求职工作台。项目目标不是做静态演示页，而是跑通真实工程闭环：上传简历、模型解析评分、真实岗位检索、投递清单、模拟面试和 Agent 对话。

## 技术栈
- Backend：FastAPI + SQLAlchemy + Alembic
- Worker：Python worker loop
- Database：PostgreSQL 16
- Cache：Redis 7
- Vector Search：Qdrant + fastembed / DashScope `text-embedding-v4`
- Frontend：Next.js 14 App Router + TypeScript + Tailwind CSS
- Gateway：nginx
- Runtime：Docker Compose
- LLM：`gemma4:26b`，固定走 Ollama `api/generate` 流式协议

## 当前能力
- 用户注册、登录、刷新 Token；开发环境内置测试账号 `admin/password`。
- PDF / DOCX 简历上传，worker 异步提取文本。
- Gemma4 结构化解析简历并按 `resume_score_v1` Rubric 评分，异常时回退规则评分；每个维度都返回依据、扣分点、修改建议和置信度。
- `GET /api/v1/resume/{id}/status` 返回阶段化进度：上传成功、文本提取、结构化解析、评分、完成；失败时给出可读原因。
- 国内岗位源默认启用：腾讯公开招聘 API、国内企业官网/校招官网入口、国聘/公告页和本地职业覆盖；可选启用猎聘官方 MCP 授权岗位源；国际 ATS（Ashby / Greenhouse / Lever）默认关闭，可用 `ENABLE_GLOBAL_ATS=true` 手动开启。
- 岗位搜索统一使用 `GET /api/v1/jobs/search?keyword=&city=&limit=`，匿名也能浏览岗位；登录且有默认简历时返回 `match_score`、推荐分、匹配技能、缺失技能、推荐理由和投递优先级。
- 国内招聘平台边界明确：企业官网、国聘/公告页、可配置第三方搜索、官方 MCP 可接入；BOSS / 智联 / 前程无忧 / 拉勾等登录态、验证码、滑块或反爬不会绕过，也不会伪造实时数据；猎聘只走官方 MCP 授权入口，不爬网页。
- 岗位发现使用 `SearchJobs` 抽象：对国内公开源、第三方搜索、seed/manual 数据做多 query expansion、城市/经验/技能过滤、title taxonomy、去重聚合和真实频次热度评分。
- 岗位搜索/发现会优先展示中国市场岗位；岗位页支持搜索建议和筛选记忆，岗位卡展示公司、城市、薪资、实习/正式、来源、推荐原因和匹配缺口，`/jobs/[id]` 是“是否适合、简历怎么改、面试问什么、开始岗位面试”的决策页。
- 首页登录后展示结构化“下一步建议”，根据简历解析、投递状态和面试报告提醒用户继续搜索岗位、原站投递、更新反馈或再练一轮。
- 投递中心采用真实边界：保存岗位、打开原站、手动确认投递、等待反馈、面试中、已结束，并支持记录投递平台、投递日期、HR 联系方式和反馈结果。
- Chat 使用最小 Agent Runtime：意图理解、任务规划、记忆、工具调用、执行控制、结果校验；主界面只展示最终对话，不暴露内部推理链路。
- Chat Agent 现在显式记录生命周期：`BeforeTurn -> BeforeReasoning -> PromptRender -> Reasoner -> AfterReasoning -> AfterTurn`，SSE metadata 只保留阶段摘要，不保存完整 Prompt、简历原文或内部推理链。
- AI 助手与模拟面试助手上下文彻底分离：AI 助手短期上下文只来自 `chat_sessions`，面试助手短期状态只来自 `interview_sessions.report.agent_state`；两者只共享默认简历、岗位、投递等事实源，AI 助手长期上下文写入 `runtime/ai_assistant_memory` 文件工作区，面试助手只保留当前 `interview_sessions.report.agent_state`。
- AI 助手长期记忆采用“两阶段归档”：先写入隐藏的 `memory_kind=pending` 并记录安全 `source_ref`，本轮输出校验后再确认成最终记忆；pending 记忆不会进入下一轮上下文。
- AI 助手已接入八股文档 Hybrid RAG：`file/10万字总结.docx` 和精选 `javaup/docs` Markdown 会先清洗、按问答/标题结构切分、注入章节/问题/来源 URL/关键词/质量分 metadata，再写入 PostgreSQL + Qdrant；技术面/Java/后端/八股问题会做 query rewrite、多查询召回、向量检索 + BM25 关键词检索、轻量 rerank、context packing 和检索充分性判断，再把核心片段交给 `gemma4:26b`。
- AI 助手 RAG 与记忆引用统一为 `citation_v1`：引用只暴露 `source_file/section_path/question/chunk_index/source_url/repo_path` 等结构化字段，不暴露 Qdrant point id、raw prompt 或检索片段中的恶意指令。
- RAG 增加检索质量评估：`backend/evals/rag/rag_eval_cases.jsonl` 定义技术问答 golden cases，`eval_knowledge_rag.py` 输出 Recall@k、MRR、Context Precision、Answer Point Coverage、Grounded Answer Rate 和 Hallucination Case Count，并记录 Hybrid / Rerank 是否启用。
- 简历评分升级为 Rubric + 证据链：固定教育背景、技能匹配、项目经历、实习/实践、表达质量、量化结果、风险项 7 个维度，并返回 `rule_score` 规则检查与 `llm_review` 模型评审摘要。
- AI 助手回答后可附带轻量行动按钮，例如搜索相关岗位、生成投递建议、开始模拟面试。
- AI 助手支持自然语言定时任务：可以识别“明天上午 9 点提醒我”“每 30 分钟检查一次岗位”“工作日早上 9 点提醒我看投递”等表达，任务持久化在 PostgreSQL，由 `notification-worker` 到点执行，结果进入任务收件箱；Telegram 创建的任务会同步回到 Telegram。
- 定时任务不是任意系统 Cron：第一版开放的是项目内 AI 助手 allowlist 工具，例如岗位搜索、简历状态、投递清单、RAG 技术问答和 AI 总结；禁止 shell、自动外部投递、验证码/反爬绕过和越权写库。
- AI 助手与模拟面试统一流式协议：`start -> delta -> end/error`，前端边生成边展示，并支持停止本轮生成。
- Telegram 接入采用 Akashic-inspired 通道设计：网页登录用户可生成一次性绑定码，手机发送 `/bind CODE` 后绑定到自己的账号；worker 轮询 Telegram 入站消息并复用现有 `ChatService` 回复，同一 Telegram 账号默认续同一个 `chat_session_id`，也支持 `/new`、`/current`、`/sessions`、`/use` 在手机上管理会话；主动推送先收集带时间戳的简历/投递候选事件，再经过安静时段、每日上限、同类冷却、已发送去重等规则闸门，最后交给 LLM 输出 `send/skip` 决策和带本地时间戳的消息。
- AI 助手和模拟面试都有会话列表，刷新后可从数据库恢复历史消息；列表会展示会话摘要、最近问题和完成度，避免只看时间戳。
- 模拟面试必须绑定一份已解析默认简历；面试助手已升级为岗位 × 简历驱动的 Agent，会维护 `job_profile/candidate_profile/question_plan/evaluation_state/difficulty`，前端展示轮次、难度、当前考察点和上一题反馈摘要，同一岗位默认继续最近会话，也可强制新开一轮。
- Agent 回归评测体系：`backend/tests/agent_eval/golden_cases/*.jsonl` 固化意图识别、工具调用、工具参数、RAG grounding、岗位匹配解释、面试问题计划、追问策略和简历评分 rubric，避免 Prompt 或工具改动后行为悄悄退化。
- Agent / RAG 评测报告化：`backend/evals/agent/run_agent_eval.py` 聚合 golden cases，报告输出到 `docs/evaluation/agent-rag-eval-report.md`；RAG 检索质量继续由 `backend/evals/rag/eval_knowledge_rag.py` 统计 Recall@k、MRR 和 groundedness。
- 面试助手主故事沉淀：`docs/evaluation/interview-agent-story.md` 记录 `JobProfile -> CandidateProfile -> QuestionPlan -> AnswerSignals -> EvaluationState -> FollowupStrategy -> SummaryReport` 的状态机和证据链。
- 安全与 trace 边界：SSE `end.metadata` 增加 `request_id/agent_run_id/eval_tags/retrieval_summary/evidence_summary/safety_boundary` 摘要；`docs/security/llm-risk-boundaries.md` 明确 prompt injection 隔离、工具 allowlist、自动投递禁用、招聘平台反爬不绕过和上下文隔离。
- 项目评审与展示材料：`docs/project-review-status.md` 是当前真实状态审计文档，按“已做到/部分做到/未做到”回答项目真实性、Agent、RAG、岗位、简历、面试、记忆、安全、测试和上线边界；`docs/resume/internagent-agent-resume.tex` 是面向 AI/Agent 工程岗位的 ATS-friendly LaTeX 简历模板。
- 前端品牌升级为“青程 AI”，整体按 `frontend-image-to-implementation` 流程重构：先用 UI mockup 确定方向，再用项目原生 Next.js/Tailwind 组件落地；首页、登录注册和简历上传页的产品预览使用 inline SVG 由前端直接绘制，不嵌入整屏位图，也不退化成纯文字流程列表。
- 前端是白底蓝色极简工作台，AI 助手与模拟面试采用 ChatGPT 风格对话页，只保留会话列表、标题、示例、消息区和底部输入框。

## 目录结构
```text
intern-agent/
  backend/
    app/
      agents/
      controllers/
      core/
      models/
      repositories/
      schemas/
      services/
      tasks/
      tools/
    evals/
    alembic/
    tests/
  frontend/
    src/app/
    src/components/
    src/lib/
  infra/nginx/
  infra/sql/
  docs/
    evaluation/
    security/
    resume/
  skills/
    chat-routing-tool/
    resume-profile-tool/
    job-search-tool/
    application-list-tool/
    knowledge-search-tool/
    assistant-memory-tool/
    interview-state-tool/
    llm-provider-tool/
    agent-evaluation-tool/
    runtime-ops-tool/
    backend-service-tool/
    frontend-ui-tool/
    telegram-notification-tool/
    scheduled-task-tool/
  docker-compose.yml
  .env.example
  .editorconfig
  README.md
```

## 代码学习路径
从零学习时不要先陷进所有文件，按“入口 -> 分层 -> 业务闭环 -> Agent 能力”的顺序读。

1. 运行与入口：先看 `docker-compose.yml`、`backend/app/main.py`、`backend/app/core/settings.py`，理解服务怎么启动、配置怎么进入后端。
2. 后端分层：`controllers/` 只接 HTTP 请求，`schemas/` 做请求响应字段校验，`services/` 编排业务规则，`repositories/` 负责数据库读写，`models/` 定义表结构。
3. 鉴权链路：读 `backend/app/controllers/auth_controller.py`、`backend/app/services/auth_service.py`、`backend/app/repositories/user_repository.py`、`backend/app/core/security.py`。
4. 简历链路：读 `resume_controller.py`、`resume_service.py`、`resume_repository.py`、`tasks/resume_tasks.py`，重点看上传、解析、评分、状态查询如何串起来。
5. 岗位链路：读 `job_controller.py`、`job_service.py`、`repositories/job_repository.py`、`tools/job_discovery/`、`scripts/sync_real_jobs.py`，理解真实岗位同步、去重、推荐分和搜索。
6. 投递链路：读 `application_controller.py`、`application_service.py`、`application_repository.py`，记住项目边界是“保存岗位 + 原站投递 + 手动跟进”，不自动外部提交。
7. Chat Agent：读 `chat_controller.py`、`chat_service.py`、`agents/supervisor.py`、`agents/runtime/lifecycle.py`、`services/assistant_memory_markdown_service.py`，理解意图、计划、工具调用、记忆和 SSE 输出。
8. 面试 Agent：读 `interview_controller.py`、`interview_service.py`、`agents/interview/`，重点看岗位画像、候选人画像、问题计划、回答评估和追问策略。
9. RAG 与评测：读 `services/knowledge_rag_service.py`、`evals/rag/`、`evals/agent/`、`tests/agent_eval/`，理解知识库检索和 golden case 如何防回归。
10. Telegram 主动通道：读 `controllers/telegram_controller.py`、`services/telegram_client.py`、`services/telegram_bridge_service.py`、`services/proactive_notification_service.py`、`tasks/telegram_tasks.py`，理解网页绑定码、手机会话命令、候选事件、规则闸门和 LLM `send/skip` 决策。
11. 前端：从 `frontend/src/app/` 的页面路由开始，再看 `frontend/src/components/` 和 `frontend/src/lib/api.ts`，把页面动作和后端接口对应起来。

代码规范上，后端不保留模板式 docstring；只在复杂业务决策、外部系统边界、安全约束处写短注释。基础格式由 `.editorconfig` 固定，Python 使用 4 空格缩进，其它常规文件使用 2 空格。

## Skills
`skills/` 现在是项目专用的工具型 Skill：大模型先读 `SKILL.md` 判断何时使用，再按说明调用项目脚本或 Docker 命令，脚本只返回 compact JSON，最终回答由大模型整理。
- `chat-routing-tool`：检查 Chat Supervisor 对某条消息的意图、计划和工具选择。
- `resume-profile-tool`：读取默认/最新简历画像、解析状态和评分摘要。
- `job-search-tool`：调用岗位发现与推荐管线，返回岗位、来源、匹配技能和缺口。
- `application-list-tool`：读取保存岗位和投递状态流。
- `knowledge-search-tool`：调用 Hybrid RAG 检索 Java/后端/八股知识。
- `assistant-memory-tool`：检查 AI 助手和面试助手长期记忆分区，也可导出运行时 Markdown 快照。
- `interview-state-tool`：检查模拟面试的 Agent 状态、轮次、难度和追问策略。
- `llm-provider-tool`：检查 Gemma4/Ollama Provider 配置和健康诊断。
- `agent-evaluation-tool`：运行 Agent golden-case 评测。
- `runtime-ops-tool`：管理 Docker Compose 启停、健康检查和运行时恢复。
- `backend-service-tool`：列出 FastAPI 路由，检查后端接口面。
- `frontend-ui-tool`：约束和验收 Next.js 前端页面、组件、测试与构建。
- `telegram-notification-tool`：检查 Telegram 双向聊天桥接、主动推送候选、LLM `send/skip` 决策、安静时段、冷却和发送结果。
- `scheduled-task-tool`：检查 AI 助手自然语言定时任务、任务收件箱、worker 执行和 Telegram 任务命令。

## 本地启动
1. 复制环境变量。
```powershell
Copy-Item .env.example .env -Force
```

2. 按需确认 Gemma4 配置。
```env
LLM_PROVIDER=claude
CLAUDE_API_KEY=sk-local
CLAUDE_BASE_URL=http://172.21.6.82:11434/v
CLAUDE_MODEL=gemma4:26b
CLAUDE_TRANSPORT=ollama_generate
CLAUDE_TIMEOUT_SECONDS=120
ENABLE_GLOBAL_ATS=false
ENABLE_LIEPIN_MCP=false
LIEPIN_MCP_URL=https://open-agent.liepin.com/mcp/user
LIEPIN_MCP_TOKEN=
EMBEDDING_PROVIDER=dashscope
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIMENSIONS=1024
DASHSCOPE_API_KEY=
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com
QDRANT_KNOWLEDGE_COLLECTION=knowledge_chunks
```

可选启用 Telegram 双向聊天与主动推送：
```env
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=123456:telegram-bot-token
TELEGRAM_ALLOWED_CHAT_IDS=123456789,@your_username
TELEGRAM_DEFAULT_USER_EMAIL=admin@example.com
TELEGRAM_TIMEZONE=Asia/Shanghai
TELEGRAM_QUIET_START_HOUR=23
TELEGRAM_QUIET_END_HOUR=8
TELEGRAM_DAILY_PUSH_LIMIT=3
TELEGRAM_SAME_TYPE_COOLDOWN_HOURS=12
TELEGRAM_NOTIFICATION_TICK_SECONDS=300
TELEGRAM_BIND_CODE_TTL_MINUTES=10
```

说明：正式绑定方式是登录网页后调用 `POST /api/v1/telegram/bind-code` 生成一次性绑定码，再在 Telegram 发送 `/bind CODE`；数据库只保存绑定码 hash。`TELEGRAM_DEFAULT_USER_EMAIL` 和 `/start` 仍保留为本地开发兜底，不作为多用户身份方案。手机端可用 `/new` 新开会话、`/new <消息>` 新开后立即提问、`/current` 查看当前会话、`/sessions` 列出最近会话、`/use <短 id>` 切换会话。主动推送不会直接群发；每次 worker tick 会先生成带时间戳的简历解析结果、投递跟进候选事件，再由规则闸门和 LLM 判断是否值得打扰。

3. 启动全部服务。
```powershell
$env:COMPOSE_BAKE='false'
docker compose up -d --build
```

4. 如需手动刷新岗位与向量数据。
```powershell
docker compose exec api python -m app.scripts.sync_real_jobs
docker compose exec api python -m app.scripts.reindex_embeddings
```

如需启用 AI 助手八股知识库 RAG，先在 `.env` 填入阿里云百炼 `DASHSCOPE_API_KEY`，再执行。DashScope 使用百炼原生 embedding endpoint；本地 Docker 里的 Qdrant 默认不需要 `QDRANT_API_KEY`，保持空即可：
```powershell
docker compose exec api python -m app.scripts.ingest_knowledge_doc --path /app/file/10万字总结.docx
docker compose exec api python -m app.scripts.ingest_javaup_knowledge
```

如果只想刷新 `javaup` Markdown 原文，不立刻向量化，可以先执行：
```powershell
docker compose exec api python -m app.scripts.ingest_javaup_knowledge --download-only
```

当前 `javaup` 知识源来自 [shining-stars-l/javaup/docs](https://github.com/shining-stars-l/javaup/tree/master/docs)，只筛选基础内功、数据库、框架中间件、进阶设计与性能优化中对 Java 后端八股价值较高的文档，不全量搬运。下载后的清单位于 `file/knowledge_sources/javaup/manifest.json`。

评估 RAG 检索和生成质量：
```powershell
docker compose exec api python -m evals.rag.eval_knowledge_rag
docker compose exec api python -m evals.rag.eval_knowledge_rag --generate-answers
```

报告会写入 `backend/evals/rag/rag_eval_report.md`，用于观察正确 chunk 是否排在前面、回答是否覆盖标准要点、是否出现未被上下文支持的断言；`--ablation` 会额外对比 dense-only / BM25-only / hybrid-rerank 的 Recall@3/5 和 MRR。

简历评分 Rubric 验收：
```powershell
docker compose run --rm api sh -c "alembic upgrade head && pytest tests/resume tests/agent_eval/test_resume_score_rubric.py -q"
cd frontend
npm test -- src/components/resume-score-card.test.tsx
```

如果没有配置 Key，脚本会明确失败：`embedding provider not configured`，不会假装已入库。

说明：`api` 容器启动时会自动等待 Postgres、执行 `alembic upgrade head`，并同步国内公开岗位目录。如果 Docker Desktop 重装或换盘导致 volume 为空，正常重启即可恢复岗位库；也可以重新执行上面的同步命令手动刷新岗位与向量索引。

开发测试账号会在 API 启动或首次登录时自动确保存在：
```text
账号：admin
密码：password
```

5. 访问入口。
```text
http://localhost
http://localhost/jobs
http://localhost/resume/upload
http://localhost/chat
```

## 常用验收
低资源静态检查，不需要启动 Docker：
```powershell
python -m compileall -q backend\app
python -c "import importlib.util, sys, pathlib; p=pathlib.Path('backend/tests/quality/test_source_readability.py'); s=importlib.util.spec_from_file_location('quality', p); m=importlib.util.module_from_spec(s); sys.modules[s.name]=m; s.loader.exec_module(m); m.test_backend_comments_and_docstrings_are_readable(); print('readability ok')"
```

完整容器级验收，执行前先确认 Docker Desktop 资源充足：
```powershell
docker compose ps
docker compose exec api pytest -q
docker compose run --rm api sh -c "alembic upgrade head && pytest tests/agent_eval -q"
docker compose exec api python -m evals.agent.run_agent_eval
docker compose run --rm frontend npm run build
curl http://localhost/health
curl http://localhost/health/provider
```

## Docker 重装 / 换盘恢复
```powershell
docker version
docker compose version
docker info --format "DockerRootDir={{.DockerRootDir}}"
docker compose pull
docker pull python:3.11-slim
$env:COMPOSE_BAKE='false'
docker compose up -d --build
docker compose exec api python -m app.scripts.sync_real_jobs
docker compose exec api python -m app.scripts.reindex_embeddings
```

如果 `frontend` 首次启动较慢，通常是新的 `frontend_node_modules` volume 正在自动执行 `npm install`。

## 关键接口
- `GET /health`
- `GET /health/provider`
- `GET /api/v1/dashboard/summary`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/resume/upload`
- `GET /api/v1/resume/{resume_id}/status`
- `GET /api/v1/jobs/search?keyword=产品经理&city=北京&limit=10`
- `GET /api/v1/jobs/discover?keyword=产品&skills=SQL`
- `GET /api/v1/jobs/{job_id}`
- `POST /api/v1/jobs/{job_id}/apply`
- `GET /api/v1/applications`
- `POST /api/v1/applications/{application_id}/mark-opened`
- `POST /api/v1/applications/{application_id}/mark-applied`
- `POST /api/v1/applications/{application_id}/mark-waiting-feedback`
- `POST /api/v1/applications/{application_id}/mark-interviewing`
- `POST /api/v1/applications/{application_id}/mark-closed`
- `PATCH /api/v1/applications/{application_id}/notes`
- `POST /api/v1/interview/session/start`
- `GET /api/v1/interview/sessions`
- `GET /api/v1/interview/session/{session_id}`
- `POST /api/v1/interview/session/{session_id}/answer/stream`
- `GET /api/v1/chat/sessions`
- `GET /api/v1/chat/sessions/{session_id}`
- `POST /api/v1/chat/stream`
- `GET /api/v1/scheduled-tasks`
- `PATCH /api/v1/scheduled-tasks/{task_id}`
- `GET /api/v1/scheduled-tasks/{task_id}/runs`
- `GET /api/v1/task-inbox`
- `PATCH /api/v1/task-inbox/{inbox_id}/read`
- `python -m app.scripts.ingest_knowledge_doc --path /app/file/10万字总结.docx`
- `python -m app.scripts.ingest_javaup_knowledge`

## 前端页面
- `/`：访客工作台 / 登录后仪表盘
- `/auth/login`：登录
- `/auth/register`：注册
- `/resume/upload`：简历上传与阶段化解析进度
- `/resume/[id]/status`：简历评分报告与失败原因
- `/jobs`：岗位搜索、搜索建议、筛选记忆、推荐解释
- `/jobs/[id]`：岗位决策页、保存、原站投递、按岗位开始/新开模拟面试
- `/applications`：投递清单、状态流和手动跟进备注
- `/interview/start`：绑定默认简历的模拟面试入口
- `/interview/[id]`：带会话列表的聊天框式面试会话
- `/interview/[id]/report`：面试报告
- `/chat`：带会话列表、Telegram 绑定、定时任务侧栏和任务收件箱的聊天框式 AI 求职助手

## 学习重点
- 文档驱动开发如何拆阶段落地。
- TDD 如何覆盖后端服务、脚本、SSE 和前端组件。
- 如何把 LLM 调用封装为 Provider，并为异常输出设计 fallback。
- 如何用 Docker Compose 管理 API、worker、frontend、nginx、Postgres、Redis、Qdrant。
- 如何把“模型调用”升级为最小 Agent：意图、计划、记忆、工具、控制、校验。
- 如何为 Agent 建立 golden case 回归评测：验证意图、工具、参数、RAG grounding、岗位解释、面试追问和评分 rubric。
- 如何把简历评分从单一分数升级为 Rubric + 证据链：规则层检查、模型层评审、fallback 透明标记、前端维度化展示。
- 如何把“岗位发现”从 prompt 枚举升级为检索系统：外部数据源、标准化、去重聚合、结构化 RAG payload。
- 如何把“一次性模型返回”升级为统一流式协议：Provider 原生流、兼容切块、SSE 增量消费和前端中断。
- 如何把本地和公开 Markdown 面试资料做成 RAG：DOCX 解析、Markdown 标题切分、来源 metadata、DashScope embedding、Qdrant 检索和 Chat 工具注入。
- 如何把基础向量库升级成可解释 Hybrid RAG：数据清洗、问答型 chunk、metadata、query rewrite、dense + BM25 retrieval、rerank、context packing 和检索充分性判断。
- 如何评估 RAG 质量：用 golden cases 统计 Recall@k、MRR、Context Precision、Answer Point Coverage 和 Grounded Answer Rate。
- 如何把 AI 助手扩展成应用内调度器：自然语言时间解析、数据库任务表、worker 扫描、执行审计、收件箱和 Telegram 同渠道回传。
- 如何把工程状态转成产品体验：简历阶段进度、岗位推荐解释、岗位决策页和面试节奏条。

## 流式对话协议
AI 助手与面试助手都使用 SSE，事件格式保持一致：

```json
{
  "type": "delta",
  "conversation_id": "uuid",
  "role": "assistant",
  "message_id": "assistant-uuid",
  "content_delta": "增量文本"
}
```

事件顺序：
- `start`：创建本轮助手消息，返回 `conversation_id/message_id/metadata`。
- `delta`：持续追加 `content_delta`。
- `end`：返回 `full_content/message_id/metadata`，完整消息已经写入会话历史。
- `error`：返回 `message/code`，前端停止生成状态。

`gemma4:26b` 当前在远端 Ollama 的 `api/generate` 流式接口下最稳定；Provider 会把 `max_tokens` 映射为 Ollama `num_predict`，避免长时间无界生成。如果某个 Provider 没有原生流，服务层会把完整文本切成小块，前端调用方式不变。

AI 助手的 `end.metadata` 还会持久化轻量产品动作：
```json
{
  "assistant_type": "ai_assistant",
  "memory_scope": {
    "short_term": "chat_sessions",
    "long_term": "runtime/ai_assistant_memory"
  },
  "knowledge_references": {
    "count": 3,
    "source": "knowledge_rag"
  },
  "agent_pipeline": {
    "phases": ["BeforeTurn", "BeforeReasoning", "PromptRender", "Reasoner", "AfterReasoning", "AfterTurn"]
  },
  "citation_protocol": {
    "version": "citation_v1"
  },
  "suggested_actions": [
    {
      "kind": "job_search",
      "label": "去搜索相关岗位",
      "href": "/jobs?keyword=产品经理"
    }
  ]
}
```

前端只把这些动作展示为小按钮，帮助用户从文本建议继续进入岗位搜索、投递建议或模拟面试，不展示内部推理链路。

长期记忆采用“共享事实源，分离上下文”的设计：
- `runtime/ai_assistant_memory/users/<user_id>/`：AI 助手长期文件化上下文，保存会话 JSONL、history 摘要、USER/MEMORY/SOUL。
- `interview_sessions.report.agent_state`：面试助手当前场次短期状态；不再维护复杂长期 interview memory。
- 两个助手都可以通过工具读取 `resumes/jobs/applications/users`，但不能互相读取对方的会话历史或长期记忆。
- AI 助手记忆写入先进入 `pending` 阶段，带 `source_ref` 指向 `request_id/agent_run_id/message_id/tool` 等安全来源；确认后才成为可召回长期记忆。
- 长期记忆会自动压缩：同一用户、同一助手、同一 scope 的普通记忆超过阈值后，最旧记忆会软删除并合并进 `memory_kind=compressed_summary`，`end.metadata.memory_updates.compaction` 会给出本轮压缩摘要。

## 面试 Agent 状态
面试助手不是每轮裸调模型，而是维护一份持久化 Agent 状态。当前状态存储在 `interview_sessions.report.agent_state`，后续可以演进到独立表或 MCP tool registry。

```json
{
  "job_profile": {
    "title": "AI Agent 工程师实习生",
    "domain_tags": ["LLM", "RAG", "Agent", "Backend"],
    "must_have_skills": ["Python", "Qdrant", "RAG"],
    "interview_focus": ["项目经历", "RAG/Agent 设计", "工程化与评测"]
  },
  "candidate_profile": {
    "skills": ["Python", "FastAPI", "Qdrant", "RAG"],
    "matched_skills": ["Python", "Qdrant", "RAG"],
    "missing_skills": []
  },
  "question_plan": [],
  "asked_questions": [],
  "evaluation_state": {},
  "difficulty": 2,
  "remaining_focus": [],
  "mcp_hooks": {
    "enabled": false,
    "tool_registry": []
  }
}
```

每轮回答后，SSE `end.metadata.agent` 会包含：
- `answer_signals`
- `evaluation_state`
- `difficulty`
- `followup_strategy`

这保证面试问题优先来自“岗位要求 × 简历证据”的交集，而不是只按岗位 JD 泛泛出题。

## 统一岗位搜索接口
前端岗位页只消费统一入口：

```text
GET /api/v1/jobs/search?keyword=产品经理&city=北京&limit=10
```

返回列表主字段：
```json
{
  "job_id": "uuid",
  "title": "产品经理实习生",
  "company": "字节跳动",
  "city": "北京",
  "salary": "220-300元/天",
  "posted_at": "2026-04-01T00:00:00",
  "apply_url": "https://jobs.bytedance.com/zh/position/...",
  "source": "official_company"
}
```

数据源优先级：实时岗位优先，腾讯公开招聘 API / 猎聘 MCP / 国内企业公开入口 / 国聘公告页 / 可配置第三方搜索 > seed/manual > `market_baseline`。`market_baseline` 只表示主流职业覆盖，方便岗位理解、RAG 和模拟面试，不声称是实时招聘岗位。国际 ATS 只有在 `ENABLE_GLOBAL_ATS=true` 时才会参与同步。

去重规则固定为两层：先按规范化 `apply_url` 指纹去重，再按 `company + canonical_title + city + job_type` 合并；合并结果通过 `merged_sources` 和 `duplicate_count` 暴露，方便排查来源。

可选第三方搜索配置：
```env
SERPAPI_API_KEY=
APIFY_TOKEN=
ENABLE_GLOBAL_ATS=false
ENABLE_LIEPIN_MCP=false
LIEPIN_MCP_URL=https://open-agent.liepin.com/mcp/user
LIEPIN_MCP_TOKEN=
LIEPIN_MCP_QUERIES=产品经理@北京;Java@北京;Java@上海;Java@深圳;后端开发@深圳;前端开发@上海;测试开发@杭州;算法工程师@北京;数据分析@上海
```

说明：`LIEPIN_MCP_QUERIES` 是启动/手动同步时的预抓取计划；岗位页搜索如果本地结果不足，还会按当前关键词和城市即时调用猎聘 MCP 补抓并入库，不需要等下一次全量同步。

## 岗位发现数据结构
`GET /api/v1/jobs/discover` 返回的每条岗位至少包含：
```json
{
  "raw_title": "Associate Product Manager Intern",
  "canonical_title": "产品经理实习生",
  "city": "Shanghai",
  "experience": "intern",
  "skills": ["SQL", "User Research"],
  "company": "腾讯",
  "source": "official_company",
  "url": "https://careers.tencent.com/jobdesc.html?postId=...",
  "salary": "200-300元/天",
  "job_type_label": "实习",
  "market_region": "CN",
  "summary": "职位摘要",
  "popularity_score": 100,
  "rag_payload": {
    "document_id": "job:official_company:<id>",
    "text": "用于向量化的岗位文本",
    "metadata": {
      "raw_title": "...",
      "canonical_title": "...",
      "skills": ["SQL"],
      "experience": "intern"
    }
  }
}
```

如果没有命中真实 ATS 数据，响应会返回 `fallback_notice`，明确说明结果来自本地种子或手工数据，不会伪装成实时市场全集。





## 2026-06-04 架构重构补充

本轮把 Agent 相关代码继续收敛成更清晰的工程结构：

- Prompt 已外置到 `backend/app/prompts/templates/`，通过 `PromptRegistry` 使用 YAML + Jinja2 渲染；Chat、Resume、Interview、Notification 的核心 prompt 不再散落在 service 字符串里。
- AI 助手新增复杂度分流：简单问题走 `simple_answer` 直答，不调用工具；复杂求职任务走 Supervisor/Agent Pipeline 和服务端 allowlist 工具。
- AI 助手长期上下文按 `方法.md` 改为文件化工作区：`runtime/ai_assistant_memory/users/<user_id>/sessions/*.jsonl`、`memory/history.jsonl`、`USER.md`、`MEMORY.md`、`SOUL.md`。PostgreSQL `chat_sessions` 仍是业务会话权威来源。
- AI 助手支持 soft consolidation：长上下文只追加摘要到 `memory/history.jsonl`，原始 `sessions/*.jsonl` 不覆盖；Dream 第一版只做 USER/MEMORY/SOUL 的最小本地编辑，不做 git commit。
- 面试助手记忆边界收窄：只使用 `interview_sessions.report.agent_state` 作为当前场次短期记忆，长场次压缩为 `agent_state.session_summary`，不再写复杂长期 interview memory。
- `/chat` 前端会话侧栏新增 Telegram 绑定入口，调用 `POST /api/v1/telegram/bind-code` 并展示 `/bind CODE`。Telegram 消息复用 AI 助手 ChatService，不接入面试助手。
- 新增 `docs/architecture/project-map.md`，按入口层、Agent 层、Prompt 层、记忆层、工具层、前端层解释当前代码目录。
