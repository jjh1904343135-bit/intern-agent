# 青程 AI / InternAgent 项目真实状态审计

生成日期：2026-06-02

本文基于当前项目文件实际扫描整理，用于回答“这个项目现在到底做到哪一步、亮点是什么、还缺什么”。本次审计读取了 `AGENT_RULES.md`、`PROGRESS.md`、`README.md`、`skills/`、后端源码、前端页面、Alembic 迁移、测试目录、评测脚本和项目文档。当前目录不是 git 仓库，因此本次不是基于 git diff，而是基于真实文件结构和最近修改时间判断。

## 一、总体定位

青程 AI 当前更准确的定位是：

```text
面向实习与校招准备的 AI 求职 Agent 工程原型。
```

它已经不是单纯页面 demo，因为后端分层、数据库迁移、Docker Compose、简历解析、岗位搜索、投递状态、AI 助手、模拟面试、RAG、记忆、评测、前端状态和 Telegram 通道都已经成体系。但它也不是生产级 SaaS，因为还缺 CI/CD、完整 E2E、生产监控、备份恢复、限流、权限负向测试、OCR/病毒扫描和稳定的大规模岗位数据源。

推荐对外表达：

```text
我做的是一个可运行的 AI 求职 Agent 平台原型，重点不是堆页面，而是把简历、岗位、RAG、Agent、记忆、投递状态、模拟面试和评测体系串成一个可验证的工程闭环。
```

## 二、完整业务闭环

### 已做到

- 用户可以从注册/登录进入系统，开发环境有 `admin@example.com` / `password` 测试账号。
- 支持 PDF / DOCX 简历上传，worker 异步处理，状态接口返回阶段化进度。
- 简历解析使用本地文本提取 + Gemma4 结构化解析 + Rubric 评分，模型异常时有规则 fallback。
- 岗位搜索统一走 `/api/v1/jobs/search`，匿名可以浏览，登录且有默认简历时返回推荐分、匹配技能、缺失技能和投递优先级。
- 投递中心遵守“保存岗位 -> 打开原站 -> 用户手动确认”的边界，不做自动外部投递。
- AI 助手支持流式对话、会话恢复、知识库检索、岗位搜索、投递建议和行动按钮。
- 模拟面试需要绑定已解析简历，并围绕岗位 × 简历交集生成问题、追问和报告。
- 前端已经产品化为“青程 AI”，不再是纯功能入口列表。

### 部分做到

- 完整链路能通过 Docker Compose 跑，但依赖 Docker Desktop、Gemma4 服务、DashScope Key、可选猎聘 MCP Token 等外部配置。
- 岗位真实度依赖腾讯公开接口、猎聘 MCP、企业公开入口等外部源；系统有兜底，但兜底不能当作实时岗位。
- worker 是 Python loop，不是成熟队列系统，可靠性还不如 Celery/RQ。

### 未做到

- 没有 Playwright 端到端测试覆盖完整用户旅程。
- 没有一键 `seed_demo.py` 把演示状态稳定恢复到固定样例。
- 没有生产级多租户 SaaS 的审计、监控、备份、限流和告警。

## 三、Agent 能力

### 已做到

- AI 助手不是纯聊天机器人，已经有受控 Agent Runtime：意图识别、任务规划、工具调用、会话记忆、长期记忆、结果校验和 SSE metadata。
- Chat Agent 生命周期记录为 `BeforeTurn -> BeforeReasoning -> PromptRender -> Reasoner -> AfterReasoning -> AfterTurn`。
- 工具调用由服务端受控调度，不允许模型直接写库。
- AI 助手可调用简历画像、岗位搜索、投递清单、知识库检索等内部工具。
- 模拟面试助手已经独立 Agent 化，状态链路是 `JobProfile -> CandidateProfile -> QuestionPlan -> AskedQuestions -> AnswerSignals -> EvaluationState -> FollowupStrategy -> SummaryReport`。
- AI 助手和面试助手上下文隔离，只共享简历、岗位、投递等事实源。

### 部分做到

- 当前更像“受控 Agent 编排层”，不是完全开放式自主 Agent。
- 工具参数有测试和约束，但还没有完整的 schema registry。
- trace 主要在 SSE metadata 和文档中，尚未沉淀成独立 `agent_runs/tool_calls/llm_calls` 表。

### 未做到

- 未接入完整 MCP tool registry，面试链路只预留 `mcp_hooks`。
- 未做可视化 Agent Trace 页面。
- 未做生产级高风险动作审批流。

## 四、RAG 能力

### 已做到

- RAG 只服务 AI 助手 `/chat`，不混入模拟面试主链路。
- 知识源包括 `file/10万字总结.docx` 和精选 `shining-stars-l/javaup/docs` Markdown。
- DOCX / Markdown 会先清洗、去噪、去重，再按章节/问题/标题结构切分。
- 每个 chunk 保留 `source_file`、`section_path`、`question`、`chunk_index`、`topic`、`keywords`、`source_url`、`repo_path`、`chunk_quality_score` 等 metadata。
- Embedding 使用 DashScope `text-embedding-v4`，1024 维，写入 Qdrant `knowledge_chunks` collection。
- 检索流程已经升级为 query rewrite、多查询、Qdrant dense retrieval、PostgreSQL lexical retrieval、轻量 rerank、context packing 和 retrieval sufficiency 判断。
- 引用协议为 `citation_v1`，不会暴露 Qdrant point id、raw prompt 或检索片段中的指令注入文本。

### 部分做到

- lexical retrieval 当前是 PostgreSQL `ILIKE` + Python 轻量评分，不是完整 BM25 引擎。
- rerank 是规则型轻量 rerank，不是 cross-encoder 或商业 rerank API。
- RAG eval 已有 Recall@k、MRR、Context Precision、Answer Point Coverage、Grounded Answer Rate，但数据集规模还小。

### 未做到

- 未做多模态/OCR 表格图片解析。
- 未接 LangSmith 等外部观测平台。
- 未做大规模人工标注 QA 集。
- 未做正式 citation validator 来校验每个生成结论是否被引用支持。

## 五、岗位数据与匹配

### 已做到

- 岗位搜索入口统一为 `GET /api/v1/jobs/search?keyword=&city=&limit=`。
- 默认偏国内岗位：腾讯公开招聘 API、国内企业公开入口、国聘/公告页、本地职业覆盖兜底。
- 可选启用猎聘官方 MCP，系统不爬猎聘网页。
- BOSS、智联、前程无忧、拉勾等需要登录、验证码、滑块或强反爬的平台不会被绕过。
- 查询支持公司 + 岗位拆解，例如“腾讯 Java”会拆成公司族和岗位同义词。
- 搜索结果做 URL 指纹和 `company + canonical_title + city + job_type` 双层去重。
- 登录且有默认简历时，岗位返回推荐分、技能匹配、缺失技能、解释和优先级。

### 部分做到

- 有 `posted_at/last_seen_at/is_active` 等字段，但定期链接巡检和 freshness dashboard 还不完整。
- 国内真实岗位覆盖受外部 API、MCP Token、查询策略影响，不能保证全量。
- taxonomy 是规则型映射，尚未经过大规模人工校准。

### 未做到

- 不做招聘平台反爬绕过。
- 没有完整岗位质量报表。
- 没有后台人工审核和纠错工作流。

## 六、简历解析与评分

### 已做到

- 支持 PDF / DOCX 上传和文本提取。
- 简历状态有 `processing -> done/failed`，失败时有可读原因。
- Gemma4 做结构化解析，异常时 fallback。
- 评分使用 `resume_score_v1`，七个维度：教育背景、技能匹配、项目经历、实习/实践、表达质量、量化结果、风险项。
- 每个维度包含分数、权重、证据、扣分点、建议和置信度。
- 同时保留 `rule_score` 和 `llm_review`，避免只有模型主观分。

### 部分做到

- 文本型 PDF 和 DOCX 可处理，但扫描版 PDF、复杂表格、多栏简历仍可能不稳定。
- 有解析和评分测试，但还没有大规模简历 golden cases。
- 评分可解释性已经增强，但缺少重复评分稳定性实验。

### 未做到

- 没有 OCR。
- 没有病毒扫描。
- 没有上传频率限制。
- 没有用户级简历删除后联动清理文件、向量和记忆的完整链路。

## 七、模拟面试

### 已做到

- 面试必须绑定默认已解析简历。
- 面试可以从岗位详情进入，同一岗位默认复用最近会话，也支持新开。
- 面试 Agent 维护岗位画像、候选人画像、问题计划、已问问题、回答信号、评分状态、难度和剩余考察点。
- 追问策略包括澄清、下钻、挑战和迁移。
- 前端展示轮次、难度、当前考察点和上一题反馈摘要。
- 报告包含通过概率、强项、短板、高频风险和下一轮建议。
- 已有面试问题计划和追问策略的 golden case 测试。

### 部分做到

- 追问策略主要靠规则和信号分析触发，再由模型生成表达。
- 报告有证据链雏形，但前端还没有完整展示“为什么问这题”的详细证据链。

### 未做到

- 未做语音面试。
- 未做代码执行面试。
- 未接面试专用 RAG。
- 未做人工标注评分样例校准。

## 八、记忆系统

### 已做到

- AI 助手长期上下文已改成文件化工作区：`runtime/ai_assistant_memory/users/<user_id>/`。
- AI 助手会把当前会话写入 `sessions/<session_id>.jsonl`，把压缩摘要追加到 `memory/history.jsonl`，并维护 `USER.md`、`MEMORY.md`、`SOUL.md`。
- PostgreSQL `chat_sessions` 仍然是业务会话权威来源，文件化记忆只是 Agent 可读上下文层。
- AI 助手支持 soft consolidation：长上下文只追加摘要，不覆盖原始 JSONL。
- Dream 第一版会根据新增 history 对 USER/MEMORY/SOUL 做最小本地编辑，不做 git commit，也不暴露内部推理。
- 面试助手已收敛为当前场次短期记忆，只读写 `interview_sessions.report.agent_state`，不再维护复杂长期 interview memory。
- AI 助手和面试助手仍保持上下文隔离，只共享简历、岗位、投递等事实源。

### 部分做到

- 文件化记忆压缩和 Dream 更新是轻量工程规则，不是复杂可解释摘要链。
- 用户暂时不能在前端查看、编辑、删除单条记忆。
- 旧 `assistant_memories` 表和脚本仍保留用于兼容历史审计数据，但当前 AI 助手运行时不再依赖它作为主记忆层。

### 未做到

- 没有用户可见记忆管理页。
- 没有隐私脱敏策略专门作用在记忆写入前。
- Dream 还没有做成定时任务、diff 审计和回滚系统。

## 九、Telegram 通道

### 已做到

- Telegram 功能默认关闭，通过 `.env` 启用。
- 支持网页登录后生成一次性绑定码，Telegram 发送 `/bind CODE` 绑定真实网页用户。
- 数据库只保存绑定码 hash，不保存明文 code。
- 同一 Telegram 账号有 sticky `chat_session_id`，不会每条消息新建会话。
- 手机端支持 `/new`、`/new <消息>`、`/current`、`/sessions`、`/use <短 id>`、`/stop`。
- worker 分离 Telegram 入站轮询和主动通知 tick，避免主动通知阻塞聊天回复。
- 主动通知候选包括简历解析结果和投递跟进，经过安静时段、每日上限、同类冷却、去重和 LLM `send/skip` 决策。
- 有 Telegram client、bridge、bind code、tasks、proactive notification 测试。

### 部分做到

- Telegram 当前是轮询模式，不是 webhook 模式。
- 主动推送候选类型还比较少。
- 发送失败有记录，但没有完整重试队列和告警。

### 未做到

- 未做生产级 webhook 部署。
- 未做复杂多渠道通知，如邮件、企业微信等。

## 十、前端产品状态

### 已做到

- 产品名已统一为“青程 AI”。
- Next.js 14 + TypeScript + Tailwind，无 UI 组件库。
- 首页是下一步建议工作台。
- 登录/注册、简历上传、简历状态、岗位搜索、岗位详情、投递中心、AI 助手、模拟面试、面试报告均有页面。
- AI 助手和面试页是极简 ChatGPT 风格，有会话列表、消息区和底部输入框。
- 首页、登录注册、简历上传有 inline SVG 产品预览。
- 组件有 Vitest 覆盖，如 JobCard、ResumeScoreCard、ChatMessageList、SessionSidebar、InterviewRhythmBar 等。

### 部分做到

- 前后端类型仍是手写同步，没有 OpenAPI 自动生成。
- 没有 Playwright 浏览器级 E2E。
- 移动端视觉已经考虑，但仍需要真机/浏览器截图复验。

### 未做到

- 没有设计系统文档。
- 没有完整无障碍测试。

## 十一、测试与评测

### 已做到

- 后端 pytest 覆盖 auth、resume、jobs、applications、chat、interview、knowledge、memory、provider、dashboard、telegram 等模块。
- 前端 Vitest 覆盖核心组件和 API 工具。
- Agent golden cases 覆盖意图、工具、参数、RAG grounding、岗位解释、面试问题、追问策略、简历 rubric。
- RAG eval 输出 Recall@k、MRR、Context Precision、Answer Point Coverage、Grounded Answer Rate 和 Hallucination Case Count。
- 技能契约测试保证 `skills/` 工具型文档和脚本结构稳定。

### 部分做到

- 目前没有 git 仓库上下文，不能用 diff 管理变更。
- Agent eval 集合是“小而硬”的回归集，还不是大规模模型行为统计。
- 最近完整 Docker 测试结果来自文档记录，本次审计未重新启动 Docker。

### 未做到

- 没有 CI。
- 没有 Playwright E2E。
- 没有多模型对比报告。
- 没有压力测试和故障注入测试。

## 十二、展示材料

### 已做到

- `README.md` 已经能作为项目主说明，包含架构、启动、接口、学习路径、RAG、岗位、SSE、面试 Agent 等。
- `PROGRESS.md` 记录了从 Day 1 到后续深度收敛、Telegram、RAG、Skills 的开发过程。
- `docs/evaluation/agent-rag-eval-report.md` 记录 Agent/RAG 评测报告。
- `docs/evaluation/interview-agent-story.md` 记录面试 Agent 状态机故事。
- `docs/security/llm-risk-boundaries.md` 记录 LLM 风险边界。
- `docs/resume/internagent-agent-resume.tex` 存在一份面向 AI/Agent 工程岗位的 ATS-friendly LaTeX 简历模板。

### 需要注意

- `docs/resume/internagent-agent-resume.tex` 当前内容在本机读取时存在中文编码显示异常，建议后续统一修成 UTF-8 可读版本，再用于正式投递。
- 本文档已经替换旧版 `project-review-status.md` 中的乱码状态说明。

## 十三、当前最值得继续做的事

1. 恢复 Docker 后跑一次完整验收：`docker compose up -d --build`、`docker compose exec api pytest -q`、前端 `npm test/typecheck/build`。
2. 给项目补一个 `seed_demo.py`，稳定准备演示用用户、简历、岗位、投递、面试会话和知识库状态。
3. 修复 `docs/resume/internagent-agent-resume.tex` 中文编码，让简历展示材料可直接使用。
4. 增加 Playwright E2E，覆盖上传简历、搜索岗位、保存投递、AI 助手、模拟面试。
5. 扩大 Agent eval 和 RAG eval cases，让“可验证 Agent/RAG 工程”成为面试主亮点。
6. 补岗位 freshness 机制：`last_verified_at`、链接巡检、过期提示和数据质量报告。
7. 补安全硬边界：权限负向测试、上传频率限制、简历删除联动清理、PII 脱敏。
8. 建议把当前目录初始化为 git 仓库或迁回已有仓库，否则后续很难判断哪些改动未写入文档。

## 2026-06-04 架构重构状态补充

本次变更后，项目的 Agent/记忆边界需要按以下状态理解：

### 已做到

- Prompt 管理从代码内硬编码升级为 `PromptRegistry + YAML + Jinja2`，模板集中在 `backend/app/prompts/templates/`。
- AI 助手有明确复杂度分流：简单问题不调工具，复杂求职任务才进入 Agent Pipeline。
- AI 助手长期上下文迁移为文件化工作区 `runtime/ai_assistant_memory/users/<user_id>/`，包括 session JSONL、history 摘要、USER/MEMORY/SOUL。
- AI 助手长上下文压缩采用 soft consolidation，保留原始会话 JSONL，不覆盖历史。
- 面试助手不再维护复杂长期记忆，只维护当前 `interview_sessions.report.agent_state`，并在长会话时写入 `session_summary`。
- Telegram 绑定入口已进入 `/chat` 前端侧栏，Telegram 入站继续复用 AI 助手 ChatService 和 AI 助手记忆，不接入面试助手。
- 新增 `docs/architecture/project-map.md`，补齐当前代码阅读地图。

### 部分做到

- Dream 第一版是规则型最小编辑，还不是完整的异步调度、diff 审计和回滚系统。
- Prompt 已集中管理，但还没有做可视化 Prompt 版本比较页面。
- AI 文件化记忆已经有测试，但还没有前端记忆管理/删除入口。

### 未做到

- 没有把 Dream 运行做成定时任务。
- 没有将 Prompt Registry 与线上灰度/AB 实验系统打通。
- 没有把 Telegram 主动推送做成生产级 webhook 与重试队列。
