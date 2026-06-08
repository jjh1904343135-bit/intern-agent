# 青程 AI / InternAgent 开发进度

## 已完成
- Day 1：项目骨架、Docker Compose、`/health`、MockProvider。
- Day 2：PostgreSQL 核心表、SQLAlchemy 模型、Alembic 初始化迁移。
- Day 3：注册、登录、刷新 Token、JWT、bcrypt。
- Day 4：简历上传、异步解析骨架、worker、状态查询。
- Day 5：Qdrant + fastembed 检索闭环、岗位搜索、匹配分。
- Day 6：投递中心最小状态机。
- Day 7：面试会话最小闭环。
- Day 8：SSE 聊天入口、README、前端聊天页。
- Day 9：Claude Provider 抽象接入与切换验证。
- Day 10-11：`gemma4:26b` 接入与协议定型，固定 `ollama_chat`。
- Day 12：Gemma4 简历评审、Dashboard Summary、应用页和聊天页产品化。
- Day 13：岗位库扩充、keyword 搜索、Provider 诊断、Chat `session_id` 续聊。
- Day 14：前端白底蓝色工具台重构、Vitest 前端测试底座。
- Day 15：真实简历解析流水线：PDF/DOCX 文本提取、Gemma4 结构化解析、Gemma4 维度评分、fallback 兜底、worker 完整处理。
- Day 16：真实岗位同步：Ashby / Greenhouse adapter、幂等 upsert、失效岗位下线、原站投递链接。
- Day 17：Agent Runtime：意图理解、任务规划、会话记忆、项目内工具调用、执行控制、结果校验、升级 SSE 事件序列。
- Day 18：极简产品前端：评分报告卡、岗位卡、折叠 Agent Trace、首页仪表盘、投递清单手动状态流。
- Day 19：Docker 重装恢复：重拉镜像、自动迁移启动、前端依赖自恢复；AI 助手与模拟面试改为聊天框式对话体验。
- Day 20：岗位发现改造：`SearchJobs` 抽象、多 query expansion、城市/经验/技能过滤、title taxonomy、去重聚合、真实频次热度分和 RAG payload。
- Day 21：AI 助手与面试助手真实流式输出：统一 `start -> delta -> end/error` SSE 协议，Provider 原生流/兼容切块，前端极简 ChatGPT 风格对话页和停止生成。
- Day 22：聊天闭环与岗位推荐增强：AI 助手支持重新生成/继续生成，停止状态可收口；面试会话增加轮次状态机；岗位发现升级为推荐评分、匹配解释、缺口分析、优先级、三层 taxonomy、多源去重、时效排序和 RAG payload 完整化。
- Day 23：会话恢复与面试简历绑定：AI 助手/模拟面试新增会话列表与详情恢复；模拟面试必须绑定已解析默认简历；开发环境内置 `admin/password` 测试账号。
- Day 24：岗位详情与岗位化面试：岗位搜索/发现优先展示中国市场岗位，列表和详情补齐公司、地点、薪资、实习/正式、来源与技能；新增岗位详情页；模拟面试默认复用同一岗位最近会话，也支持强制新开一轮，并将岗位 JD 注入开场问题和反馈 prompt。
- Day 25：国内岗位源与统一搜索接口：新增 `JobSourceAdapter`/`JobSourceRecord` 聚合层，接入国内企业公开入口、国聘/公告页、Lever 与可配置第三方搜索；`/api/v1/jobs/search` 支持 `keyword/city/limit`，匿名可看岗位，结果强制 URL + 组合键去重，并用 `market_baseline` 覆盖主流面试职业但明确不伪装实时岗位。
- Day 26：面试助手 Agent 化：新增 `backend/app/agents/interview/`，将岗位理解、简历结构化、问题规划、回答信号分析、实时评分、难度调节、追问策略和总结反馈拆成独立模块；面试问题优先围绕“岗位 × 简历”交集发问，Agent 状态持久化到 `interview_sessions.report.agent_state`，并预留 `mcp_hooks`。
- Day 27：求职体验闭环打磨：简历上传/状态接口新增阶段化 progress 和失败原因；岗位搜索页新增搜索建议与筛选记忆；登录且有默认简历时 `/api/v1/jobs/search` 返回推荐分、匹配技能、缺失技能、解释和优先级；岗位卡与详情页升级为投递决策体验；面试页展示轮次、难度、当前考察点和上一题反馈，报告页展示通过概率、强项、短板、高频风险和下一次练习建议。
- Skill 清理：删除按 Day 命名的历史 skill，把重复能力合并为能力型 skill：Docker/后端基础/LLM Provider/简历流水线/岗位搜索推荐/投递工作流/Chat Agent/面试 Agent/前端产品体验。
- 中优先级体验增强：AI 助手回复新增可点击行动按钮；Dashboard 从数据汇总升级为结构化下一步建议；投递中心补齐 `saved -> opened -> applied_manual -> waiting_feedback -> interviewing -> closed` 状态流和手动备注；聊天/面试会话列表展示摘要、最近问题和完成度；关键空状态保留直达动作入口。
- 国内公开岗位源增强：默认关闭国际 ATS，新增腾讯公开招聘 API adapter，并扩充国内企业官网/校招官网/国聘公告页公开入口目录；岗位同步不需要用户登录，BOSS/猎聘/智联等仍只记录不可直连原因，不绕过风控。
- 青程 AI 前端整体重构：按 `frontend-image-to-implementation` 生成 UI mockup 后，用现有 Next.js/Tailwind 组件体系收敛品牌、全局视觉、首页、登录注册、简历、岗位、投递、AI 助手和模拟面试页面，减少工程说明文案，强化真实求职行动流。
- 青程 AI SVG 视觉层修正：首页、登录注册和简历上传页新增项目内 inline SVG 产品预览，不再把 mockup 视觉退化成纯文字流程列表，也不嵌入整屏位图。
- 岗位数据启动保障修复：API 启动链路切换为 `bootstrap_job_catalog -> sync_real_jobs`，新数据库或重启后会自动同步国内公开岗位目录并重建索引，避免岗位页空数据。
- 后端无用代码清理：删除已被真实岗位同步替代的旧 `seed_jobs.py` 演示脚本，测试改为验证 `sync_real_jobs` 国内岗位目录；清理 backend 下的 Python/pytest 生成缓存。
- 猎聘 MCP 岗位源接入：新增 `liepin_mcp` 官方授权 MCP adapter，配置来自 `.env`，不爬猎聘网页；MCP 返回字段统一标准化为 `JobSourceRecord`，进入现有同步、去重、排序、索引和 `/api/v1/jobs/search` 管线，实时岗位优先于静态目录。
- 岗位页数据恢复与提示修正：确认后端 pytest 会清空开发库岗位数据并留下少量测试岗位；已重新同步猎聘/腾讯岗位并重建索引，且前端在 `liepin_mcp` 可用时不再把“猎聘网页不可爬”误提示为“猎聘不可用”。
- 岗位搜索即时补抓：`/api/v1/jobs/search` 在本地结果为空或猎聘结果不足时，会按当前 `keyword/city` 调用猎聘 MCP 补抓并入库，使用 `deactivate_missing=False` 避免一次关键词搜索误下线其他猎聘岗位；预同步查询已扩展 Java/前端/测试/算法等工程岗。
- Agent 回归评测体系：新增 `backend/tests/agent_eval/golden_cases/*.jsonl` 与 7 组评测测试，覆盖 AI 助手意图识别、工具调用、工具参数、RAG grounding、岗位匹配解释、面试问题计划、追问策略和简历评分 rubric；同时修复投递跟进意图误判、`Java 后端` 关键词抽取过窄、Prompt 输出契约与安全 guardrails 不够硬的问题。
- RAG 检索质量评估体系：新增 `backend/evals/rag/rag_eval_cases.jsonl`、`eval_knowledge_rag.py` 和 `rag_eval_report.md`，支持 Recall@3/5、MRR、Context Precision、Answer Point Coverage、Grounded Answer Rate、Hallucination Case Count；AI 助手前端会在技术回答下轻量展示“参考知识”和 chunk 编号。
- AI 助手 Hybrid RAG 升级：八股文档入库增加清洗、去噪、去重、问答型 chunk、关键词/topic/quality metadata；检索从单一路向量召回升级为 query rewrite + multi-query + Qdrant dense search + PostgreSQL BM25 lexical search + 轻量 rerank + context packing + retrieval sufficiency，不做用户反馈、多模态/OCR 或外部 LangSmith。
- JavaUp 八股知识源扩展：新增精选 `shining-stars-l/javaup/docs` Markdown 抽取能力，只筛选基础内功、数据库、框架中间件、进阶设计与性能优化中对 Java 后端面试价值高的文档；下载文件落在 `file/knowledge_sources/javaup/`，并可通过 `ingest_javaup_knowledge` 进入同一个 `knowledge_chunks` RAG 管线。
- Agent Pipeline / 记忆归档 / Citation 协议：AI 助手流式 metadata 新增 `agent_pipeline`，固定生命周期为 `BeforeTurn -> BeforeReasoning -> PromptRender -> Reasoner -> AfterReasoning -> AfterTurn`；长期记忆改为先写隐藏 `pending` 候选并记录安全 `source_ref`，本轮校验后再确认归档；RAG 与记忆引用统一为 `citation_v1`，清洗 Qdrant point id、raw prompt 和检索片段中的指令注入文本。
- 简历评分 Rubric 证据链：评分结构升级为 `resume_score_v1`，固定教育背景、技能匹配、项目经历、实习/实践、表达质量、量化结果、风险项 7 个维度；每个维度返回分数、权重、依据、扣分点、修改建议和置信度，同时保留 `rule_score` 与 `llm_review` 两层来源。
- 实习面试深度收敛：新增 `backend/evals/agent/run_agent_eval.py` 聚合 Agent golden cases，报告落到 `docs/evaluation/agent-rag-eval-report.md`；新增 `docs/evaluation/interview-agent-story.md` 固化面试 Agent 状态机和三轮追问证据链；新增 `docs/security/llm-risk-boundaries.md` 说明 prompt injection、工具 allowlist、上下文隔离和招聘平台合规边界；Chat/Interview SSE metadata 补齐 `request_id/agent_run_id/eval_tags/retrieval_summary/evidence_summary/safety_boundary`。

## 当前状态
- LLM Provider：`claude` 抽象名，实际协议固定为 Ollama `api/generate` 流式生成。
- 模型：`gemma4:26b`。
- Base URL：`http://172.21.6.82:11434` 或兼容 `/v` 结尾配置，Provider 会取根地址。
- Embedding：岗位/简历索引仍可使用 Qdrant + fastembed；AI 助手八股知识库 RAG 固定使用 DashScope `text-embedding-v4`（1024 维），需要在 `.env` 填 `DASHSCOPE_API_KEY` 后执行 `ingest_knowledge_doc` 和 `ingest_javaup_knowledge` 入库。
- 简历：worker 负责 `processing -> done/failed`；状态接口提供 `progress.current_stage/stages/failure_reason`；评分结果稳定返回 `source/model/status/rubric_version`，并按 Rubric 展示依据、问题和建议，Gemma4 异常时使用同结构 `fallback_rule`。
- 岗位：统一入口为 `GET /api/v1/jobs/search?keyword=&city=&limit=`；API 启动时自动同步国内公开岗位目录并重建索引；默认启用国内公开源和本地职业覆盖兜底，可用 `ENABLE_LIEPIN_MCP=true` 接入猎聘官方 MCP，可用 `ENABLE_GLOBAL_ATS=true` 接入国际 ATS；匿名可浏览基础岗位，登录且有默认简历时返回 `match_score/recommendation_score/matched_skills/missing_skills/explanation/application_priority`；真实岗位 `apply_url` 必须指向原站，禁止 `example.com`。
- 投递：边界为“保存岗位 + 原站手动投递 + 用户确认”，不做自动外部提交；投递中心支持等待反馈、面试中、已结束以及平台/日期/HR/反馈备注。
- Agent：Chat 内部仍执行意图理解、任务规划、记忆、工具调用和结果校验，并新增显式 `agent_pipeline` 生命周期摘要；AI 助手技术面/Java/后端/八股问题会触发 `knowledge_search`，使用 query rewrite、多查询、dense + BM25 hybrid retrieval、rerank、context packing 和 sufficiency 判断检索 `knowledge_chunks`，再把命中片段注入 prompt，前端可展示参考知识来源；RAG 质量可通过 `python -m evals.rag.eval_knowledge_rag` 生成报告；AI 助手短期上下文只读 `chat_sessions`，长期只写 `assistant_memories:ai_assistant`，且先写 `pending + source_ref` 后确认归档；面试助手已具备岗位画像、候选人画像、问题计划、回答信号、实时评分、难度调节和追问策略，短期状态只读写 `interview_sessions.report.agent_state`，长期只写 `assistant_memories:interview_assistant`；两者只共享简历、岗位、投递等事实源，不互读对方会话或记忆；长期记忆超过阈值会自动软删除旧项并合并到 `compressed_summary`，避免无限增长；对外 SSE 收敛为 `start -> delta -> end/error`，metadata 持久化 provider/model/latency/delta_count/interrupted/tool/agent/memory 摘要，并通过 `citation_protocol=citation_v1` 规范 RAG/记忆引用，不在主聊天界面暴露内部推理链路。
- Trace / 安全边界：当前采用轻量实现而非完整 OpenTelemetry SDK；每次 AI 助手或面试流式运行都会产生 `request_id` 和 `agent_run_id`，metadata 只记录工具、检索、证据和安全摘要，不记录完整 prompt、完整简历原文、密钥或内部推理链；RAG chunk 和 JD/简历内容在 prompt 中被标记为不可信参考资料。
- 前端：产品名为“青程 AI”，Next.js 14 + TypeScript + Tailwind，禁止 UI 组件库；首页展示下一步建议并使用 inline SVG 产品预览承接 mockup 视觉；简历页展示上传/提取/解析/评分进度；岗位页保留搜索建议和筛选记忆，岗位卡突出推荐原因；岗位详情是决策页；投递中心展示状态流和备注；`/chat` 与 `/interview/[id]` 使用极简 ChatGPT 风格布局，面试页额外展示紧凑节奏条，不暴露内部推理链路。
- Skills：当前 `skills/` 已重构为项目专用工具型 Skill，目录包括 `chat-routing-tool`、`resume-profile-tool`、`job-search-tool`、`application-list-tool`、`knowledge-search-tool`、`assistant-memory-tool`、`interview-state-tool`、`llm-provider-tool`、`agent-evaluation-tool`、`runtime-ops-tool`、`backend-service-tool`、`frontend-ui-tool`、`telegram-notification-tool`；每个 Skill 说明触发条件、项目模块、脚本/命令、JSON 输出契约和自然语言整理规则。
- 测试账号：开发环境自动确保 `admin@example.com` 存在，前端可用 `admin/password` 登录。

## 常用验收命令
```powershell
python -m compileall -q backend\app
python -c "import importlib.util, sys, pathlib; p=pathlib.Path('backend/tests/quality/test_source_readability.py'); s=importlib.util.spec_from_file_location('quality', p); m=importlib.util.module_from_spec(s); sys.modules[s.name]=m; s.loader.exec_module(m); m.test_backend_comments_and_docstrings_are_readable(); print('readability ok')"
$env:COMPOSE_BAKE='false'
docker compose up -d --build
docker compose exec api pytest -q
docker compose run --rm api sh -c "alembic upgrade head && pytest tests/agent_eval -q"
docker compose exec api python -m evals.agent.run_agent_eval
docker compose exec api python -m evals.rag.eval_knowledge_rag
docker compose exec api python -m app.scripts.ingest_javaup_knowledge
cd frontend
npm test
npm run typecheck
npm run build
```

## 更新记录
- 2026-06-06：修复 AI 助手三项核心行为：定时任务识别补齐“一分钟后/每周一”等自然表达；自然岗位搜索如“帮我搜一下美团开发岗”稳定进入 `agentic_task -> job_search`；ChatService 增加纯文本输出清洗，流式输出和落库内容会去除 Markdown 标题、加粗、列表符号和代码块标记。容器内后端全量 `pytest -q` 已通过 219 个测试。
- 2026-04-19：完成真实闭环升级。简历解析从 mock 升级为文本提取 + Gemma4 结构化解析 + 评分；岗位同步接入 Ashby / Greenhouse；Chat 引入最小 Agent Runtime；前端重构为更像真实 App 的工作台。
- 2026-04-20：修复 Docker 重装/换盘后的启动问题，Compose 自动等待 Postgres、自动迁移、前端依赖自恢复；AI 助手和模拟面试会话重构为聊天框式界面。
- 2026-04-20：完成岗位发现真实检索改造，新增结构化发现 API 与 Agent 工具输出，不再依赖模型主观枚举岗位。
- 2026-04-20：完成 AI 助手与面试助手真实流式改造，新增面试流式回答接口，前端支持增量渲染和中断生成。
- 2026-04-21：完成聊天体验与岗位推荐闭环增强：AI 助手 regenerate/continue，面试 session 状态机，推荐评分和解释，taxonomy/去重/时效/RAG 数据质量防线，前端消息操作与轻量推荐展示。
- 2026-04-21：完成会话列表与恢复、面试-简历绑定、默认 admin 测试账号；刷新 `/chat` 和 `/interview/[id]` 后可从数据库恢复历史。
- 2026-04-23：完成岗位详情、中国市场优先展示和岗位化面试会话；同一岗位默认继续最近会话，也可以从详情页或面试入口新开一轮。
- 2026-04-24：完成 Day 25 国内岗位源和统一搜索接口，前端岗位页切换到 `/api/v1/jobs/search`，增加城市/数量过滤；BOSS/猎聘/智联/前程无忧/拉勾等需要登录、验证码或反爬的平台只记录不可直连原因，不绕过风控也不伪造实时岗位。
- 2026-04-26：完成 Day 26 面试助手 Agent 化，问题从“岗位驱动”升级为“岗位 × 简历交集驱动”，每轮回答都会写入 `answer_signals/evaluation_state/difficulty/followup_strategy`，三轮后生成结构化总结。
- 2026-05-06：完成 Day 27 体验闭环打磨，补齐简历阶段进度、岗位推荐解释、岗位详情决策区、岗位筛选记忆和面试节奏/报告摘要。
- 2026-05-06：清理 `skills/`，将 36 个 Day 型 skill 合并为 9 个能力型 skill，并删除重复/乱码/低复用的历史文件。
- 2026-05-07：完成中优先级体验增强，补齐聊天行动按钮、Dashboard 下一步建议、投递状态流/备注、会话摘要和空状态行动入口。
- 2026-05-07：完成国内公开岗位源增强，新增 `tencent_official` 实时公开 API adapter，扩充 `official_company_catalog/public_board`，并通过 `ENABLE_GLOBAL_ATS=false` 默认避免国际岗位进入同步。
- 2026-05-07：完成“青程 AI”前端整体重构，品牌从 InternAgent 展示名升级为青程 AI，并用 mockup 驱动方式收敛白底蓝色极简求职 App 体验。
- 2026-05-07：修正前端 mockup 落地偏差，新增 `qingcheng-visuals` SVG 组件并接入首页、登录注册和简历上传页，视觉预览全部由前端 SVG 绘制。
- 2026-05-07：修复岗位空数据根因，新增 `bootstrap_job_catalog` 并接入 FastAPI lifespan；启动后会自动执行 `sync_real_jobs`，当前手动验收已恢复 59 条 active 岗位并完成索引。
- 2026-05-08：清理后端旧 seed mock 岗位脚本和生成缓存，Docker 镜像已重建，容器内确认 `/app/app/scripts/seed_jobs.py` 不存在。
- 2026-05-08：接入猎聘官方 MCP 授权岗位源，实测 `fetch_liepin_mcp_jobs` 返回 158 条岗位，同步后数据库进入 211 条岗位、索引 212 条；`产品经理 + 北京` 搜索结果已优先展示 `liepin_mcp` 实时岗位。
- 2026-05-08：修复跑完 pytest 后岗位页只剩测试夹具的问题，重新执行同步后当前 API `产品经理 + 北京` 返回 10 条且前 5 条为 `liepin_mcp`；更新 Docker skill，提醒测试后必须恢复岗位库。
- 2026-05-08：修复 Java 搜索结果少的问题，新增猎聘 MCP on-demand refresh；前端提示改为“猎聘 MCP 已接入；BOSS/智联/前程无忧/拉勾不绕过风控”，避免误解为猎聘未接入。




- 2026-05-09：修复 Gemma4 健康诊断超时问题，`ollama_generate` 的 `/health/provider` 改为短流式探测，继续区分 `tag_reachable/generation_reachable`。
- 2026-05-09：修复公司 + 岗位组合搜索的通用解析问题，`腾讯Java`、`阿里Java`、`字节算法` 等查询会拆成公司族 + 岗位同义词；`大厂Java` 会按腾讯、阿里、字节、百度、美团等命名公司补抓授权岗位，不再退化为完整短语搜索。
- 2026-05-09：完成 AI 助手八股文档 RAG 底座，新增 `knowledge_documents/knowledge_chunks`、DashScope `text-embedding-v4` adapter、DOCX 切分入库脚本、Qdrant `knowledge_chunks` 检索和 Chat `knowledge_search` 工具；能力只接入 AI 助手，不改模拟面试助手主链路。
- 2026-05-09：完成八股文档 RAG 实测入库修复，DashScope adapter 切换为百炼原生 embedding endpoint，批量断连时自动拆分并对单条网络断连做有限重试；`10万字总结.docx` 已入库 917 个 chunk，PostgreSQL 与 Qdrant `knowledge_chunks` 数量一致，AI 助手 SSE metadata 已能返回 `knowledge_search` 命中。
- 2026-05-09：完成 AI 助手 / 面试助手上下文与长期记忆隔离，新增 `assistant_memories` 表与仓储；AI 助手只写 `assistant_type=ai_assistant` 的求职偏好和最近意图，面试助手只写 `assistant_type=interview_assistant` 的面试表现总结；SSE metadata 增加 `assistant_type/memory_scope/memory_used/memory_updates` 摘要。
- 2026-05-11：完成长期记忆自动压缩；`AssistantMemoryRepository` 在同一用户、助手、scope 的普通记忆超过阈值时自动生成/更新 `compressed_summary`，旧记忆只软删除不物理删除，Chat/Interview 的 `memory_updates.compaction` 会返回本轮压缩数量。
- 2026-05-13：完成 Agent 回归评测体系，新增 `tests/agent_eval` golden cases 与评测测试；TDD 首轮捕获并修复投递跟进误判为岗位搜索、`Java 后端` 工具参数丢失 Java、Prompt 缺少输出契约和安全边界的问题。
- 2026-05-13：完成 RAG 检索质量评估底座，新增 `backend/evals/rag` 数据集、指标脚本和报告模板；前端 AI 助手技术回答新增“参考知识”来源展示，metadata 保留 `chunk_index` 但不暴露 Qdrant point id。
- 2026-05-14：完成简历评分 Rubric 证据链升级，`GET /api/v1/resume/{id}/status` 的 `score` 增加 7 维度证据链、`rule_score` 检查项和 `llm_review` 模型评审摘要；前端评分卡展示依据、扣分点和修改建议。
- 2026-05-18：完成实习面试深度收敛第一轮，补齐 Agent eval 聚合脚本、面试 Agent 状态机文档、LLM 风险边界文档、SSE trace metadata、岗位推荐证据维度前端展示和 RAG prompt injection 边界测试；Docker 当前未启动，容器级 pytest 需在 Docker Desktop 恢复后复验。
- 2026-05-21：完成 AI 助手八股知识库 Hybrid RAG 升级，新增数据清洗、问答型 chunk metadata、query rewrite、多路召回、关键词检索、轻量 rerank、context packing 和检索充分性判断；本轮不做用户反馈、多模态/OCR、LangSmith 或面试助手 RAG 接入。
- 2026-05-21：扩展 JavaUp Markdown 八股知识源，新增 `ingest_javaup_knowledge` 脚本、精选路径选择器、Markdown 标题切块和来源 metadata；已下载 59 个精选 Markdown 到 `file/knowledge_sources/javaup/`，Docker 未启动时暂未执行向量化入库。
- 2026-05-21：完成 akashic-agent 启发的轻量化收敛：新增 Chat Agent 生命周期 recorder、`assistant_memories.source_ref` 迁移、pending -> confirmed 两阶段记忆归档，以及 `citation_v1` RAG/记忆引用清洗协议；已完成 Python 编译和纯单元烟测，Docker/pytest 需 Docker Desktop 恢复后复验。
- 2026-05-25：完成项目专用工具型 Skills 重构后的全量测试收口；修复面试追问难度恢复、简历 fallback 技能检测、知识库题号空格保留、RAG query rewrite/hybrid 标记，以及 `tests/evals` 与源码 `evals` 包名冲突；Docker 后端 `pytest -q`、技能契约/validator、前端 test/typecheck/build 均已通过，并在测试后恢复岗位库与索引。
- 2026-05-25：完成产品级 Agent 长期记忆 Markdown 快照设计与第一版实现；`assistant_memories` 继续作为权威存储，AI 助手与面试助手会在 `/app/runtime/memory/users/<user_id>/` 下生成隔离的 `ai_assistant.md` / `interview_assistant.md`，后续轮次可读取这份安全摘要作为长期上下文；`assistant-memory-tool` 新增 `export_memory_md.py` 方便演示和验收。
- 2026-05-27：完成学习友好的代码规范化第一轮：新增 `.editorconfig`，新增 `backend/tests/quality/test_source_readability.py` 约束后端注释/docstring 可读性，清理 `backend/app` 内模板式 `中文注释：` docstring 与乱码标记，只保留少量解释业务边界的短注释；README 增加从零读代码路径并同步当时 12 个工具型 Skills。为避免本机资源再次被 Docker 打满，本轮只执行本地静态验收，容器级回归需在确认 Docker Desktop 资源充足后再跑。
- 2026-05-30：接入 Akashic-inspired Telegram 通道与主动推送底座：新增 Telegram Bot HTTP client、Telegram 入站桥接、Telegram 账号绑定表、主动推送事件日志表、worker 轮询任务和 LLM `send/skip` 决策器；主动候选第一版覆盖简历解析结果和投递跟进，消息强制带本地时间戳，并通过安静时段、每日上限、同类冷却、同事件去重控制打扰频率。
- 2026-05-31：修复 Telegram worker 与会话连续性：worker 增加异常日志，并将用户消息轮询与主动通知 tick 隔离，避免主动通知阻塞聊天回复；`telegram_accounts` 新增 `chat_session_id`，同一个 Telegram 会话会复用同一个 ChatSession，不再每条消息新建会话。
- 2026-05-31：补齐 Telegram 多用户绑定与手机会话管理：新增登录态 `POST /api/v1/telegram/bind-code` 一次性绑定码，Telegram `/bind CODE` 可绑定到真实网页用户且数据库只保存 hash；手机端支持 `/new`、`/new <消息>`、`/current`、`/sessions`、`/use <短 id>`，保留 `/start` 默认用户绑定作为本地开发兜底。
- 2026-06-02：完成项目真实状态审计并重写 `docs/project-review-status.md`，替换旧版乱码内容；审计基于当前文件结构、后端源码、前端页面、迁移、测试、评测脚本和 Skills，而不是 git diff，因为当前目录不是 git 仓库。
- 2026-06-02：补充项目展示材料记录：`docs/resume/internagent-agent-resume.tex` 已存在一份面向 AI/Agent 工程岗位的 ATS-friendly LaTeX 简历模板；当前本机读取时中文存在编码显示异常，后续建议统一修成 UTF-8 可读版本再用于正式投递。
- 2026-06-04：修复 JavaUp 知识源入库链路，`ingest_javaup_knowledge` 现在优先读取 `file/knowledge_sources/javaup/manifest.json` 与本地 Markdown，只有显式刷新或本地缺失时才访问 GitHub；RAG lexical 召回升级为 BM25 风格打分，并新增 `eval_knowledge_rag --ablation` 对比 dense-only / BM25-only / hybrid-rerank。实测 8 个 RAG golden cases：dense-only Recall@5=0.75、BM25-only Recall@5=0.38、hybrid-rerank Recall@5=1.00，Hybrid MRR=0.71。

- 2026-06-04：完成青程 AI Agent 架构重构。Prompt 统一抽取到 `backend/app/prompts/templates/` 并由 `PromptRegistry` 注入变量；AI 助手新增 `simple_answer/agentic_task` 复杂度分流；AI 助手长期上下文改为 `runtime/ai_assistant_memory/users/<user_id>/` 文件化记忆，包含 `sessions/*.jsonl`、`memory/history.jsonl`、`USER.md`、`MEMORY.md`、`SOUL.md`，支持 soft consolidation 与 Dream 最小编辑；面试助手收敛为当前 session 短期记忆，只写 `interview_sessions.report.agent_state` 和可选 `session_summary`；`/chat` 前端新增 Telegram 绑定入口并复用 AI 助手上下文；新增 `docs/architecture/project-map.md`，同步更新 chat-routing、assistant-memory、interview-state、telegram-notification skills。

- 2026-06-05：新增 AI 助手自然语言定时任务能力；ChatService 前置识别提醒/周期/cron/列表/暂停/恢复/取消意图，新增 `assistant_scheduled_tasks`、`assistant_scheduled_task_runs`、`assistant_task_inbox` 三张表；`notification-worker` 每轮扫描到期任务并复用 AI 助手 allowlist 工具执行，结果写入任务收件箱，Telegram 创建的任务同步回 Telegram；`/chat` 侧栏新增定时任务和任务收件箱面板，新增 `skills/scheduled-task-tool`。

## 2026-06-06 运行态修复
- 修复 admin 登录后 Telegram 侧栏仍显示“绑定 Telegram”的问题：新增 `GET /api/v1/telegram/status`，前端 `/chat` 先读取绑定状态，已绑定时展示脱敏 chat_id 和已绑定状态。
- 恢复当前 admin 开发账号的 3 条 AI 历史会话与 Telegram 绑定；定时任务和任务收件箱因此前全量测试清库无法从数据库恢复，需要重新创建。
- 新增测试隔离要求：不得在开发演示库上直接运行会清空业务表的全量测试；全量回归必须使用独立测试库，或先备份并确认可恢复 admin 会话、Telegram 绑定、任务和岗位数据。

## 2026-06-07 Telegram 主动推送修复
- 排查确认：2026-06-06 晚上到 2026-06-07 早上 Docker 服务持续运行，但 admin 没有简历、投递记录或定时任务，因此旧主动推送规则没有候选事件可发。
- 修复：主动推送新增 `onboarding_nudge` 候选；当已绑定 Telegram 的用户没有简历、投递和定时任务时，每天最多推送一次低频引导。
- 修复：主动推送执行时尊重 `TELEGRAM_ALLOWED_CHAT_IDS`，跳过测试账号或非授权 chat_id，避免数据库测试残留导致错误发送。
- 修复：`notification_events.reason` 统一截断到数据库字段长度，避免 LLM 给出过长 reason 时消息已发送但审计记录写入失败。
- 验证：`tests/telegram/test_proactive_notifications.py` 10 passed；`tests/telegram/test_telegram_tasks.py` 与 `tests/scheduled_tasks/test_scheduled_task_worker_and_telegram.py` 5 passed；`compileall app` passed；admin 已在 2026-06-07 11:30 收到一条 onboarding 引导推送并记录为 sent。

## 2026-06-08 Telegram 定时任务与主动推送体验修复
- 修复 Telegram 创建定时任务后结果不可见的问题：TelegramBridge 调用 ChatService 时现在传入 `channel=telegram` 和当前 `telegram_chat_id`，创建出的任务会保存为 `source_channel=telegram`、`delivery_channel=telegram`，执行结果会直接发回同一个 Telegram 聊天，同时保留到任务收件箱。
- 改善 Telegram 定时任务创建回复：不再只说“结果会进入任务收件箱”，Telegram 来源会明确提示“会直接发到当前 Telegram 聊天，并同步进入任务收件箱”；时间格式从 ISO `T` 改为 `YYYY-MM-DD HH:mm`。
- 移除每日空状态 onboarding 主动推送：主动推送不再因为“没有简历/投递/任务”每天打扰用户，只保留真实事件候选，并继续由模型在规则门控后判断 send/skip。
- 收紧 proactive prompt：强制简体中文，产品名使用“青程 AI”，禁止低价值 onboarding/generic check-in 英文消息。
- 验证：`tests/scheduled_tasks/test_scheduled_task_service.py`、`tests/scheduled_tasks/test_scheduled_task_worker_and_telegram.py`、`tests/telegram/test_proactive_notifications.py`、`tests/prompts/test_prompt_registry.py` 共 20 passed；`compileall app` passed；强制 proactive tick 返回 0，确认空状态不再乱发。
