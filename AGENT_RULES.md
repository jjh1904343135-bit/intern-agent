# InternAgent Agent 行为准则

## 每次恢复上下文
1. 读取 `AGENT_RULES.md`。
2. 读取 `PROGRESS.md`。
3. 读取 `skills/` 下所有 `SKILL.md`。
4. 输出当前进度确认，再执行用户指定任务。

## 固定执行原则
- 只在 `intern-agent/` 项目目录内操作文件。
- 禁止删除文件，除非用户明确同意。
- 所有服务通过 Docker Compose 运行。
- 新功能和 bugfix 默认采用 TDD：先写测试，确认失败，再实现，通过后重构。
- 不得在开发演示库上直接运行会清空业务表的全量测试；需要全量回归时，必须先使用独立测试库，或先备份并确认可恢复 admin 会话、Telegram 绑定、任务和岗位数据。
- 不引入 OpenAI 服务调用；当前唯一真实模型为 `gemma4:26b`，通过 Ollama `api/generate` 流式协议访问。
- 不一次性跳过阶段；每轮交付必须本地可验证。

## 输出要求
- 说明做了什么、为什么这样做、是否影响已有文件。
- 关键改动需要同步 README / PROGRESS / skills。
- 验收必须提供实际执行过的命令和结果。

## Skill 文件规范
路径统一为：`skills/<capability-name>/SKILL.md`。
Skill 以可复用能力命名，不再按 Day 命名；内容至少包含适用场景、输入、执行步骤、验收标准、常见故障排查。
