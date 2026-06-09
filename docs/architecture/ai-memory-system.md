# AI 小助手五层记忆系统

这套记忆只属于 AI 小助手，目录在每个用户自己的 runtime workspace 里：

```text
runtime/ai_assistant_memory/users/<user_id>/
  sessions/<session_id>.jsonl
  memory/history.jsonl
  memory/MEMORY.md
  USER.md
  SOUL.md
  .dream/state.json
```

## 五层和一个原始归档

1. `session.messages`
   当前聊天窗口的短期记忆，来源是数据库里的 `chat_sessions.messages`。模型本轮真正看到的是这里的近期对话加上文件记忆摘要。

2. `sessions/<session_id>.jsonl`
   当前会话的原始归档。每一轮用户和助手消息都会追加进去，用来审计、恢复和后续压缩。它是归档落点，不直接塞进长上下文。

3. `memory/history.jsonl`
   Consolidator 的压缩摘要。上下文估算达到模型窗口约 50% 时，会压缩最旧的一批消息，只保留最近 6 条原始消息给模型，并把摘要追加到这里。

4. `USER.md`
   用户档案。保存用户身份、所在地、长期偏好、稳定目标等“不应该反复问”的事实。

5. `SOUL.md`
   沟通风格。保存小助手应该如何说话，例如简洁、直接、偏行动建议。

6. `memory/MEMORY.md`
   项目知识和长期决策。保存工具配置、架构选择、已验证方案、失败尝试等项目层面的集体智慧。

> 这里说“五层”时，核心是 `session.messages`、`history.jsonl`、`USER.md`、`SOUL.md`、`memory/MEMORY.md`；`sessions/*.jsonl` 是配套的原始归档层。

## 什么时候写入

- 普通聊天结束后：
  - 用户消息和助手回复追加到 `sessions/<session_id>.jsonl`。
  - 如果上下文超过阈值，旧消息被压缩摘要追加到 `memory/history.jsonl`。

- `/dream` 或 worker 定时 tick：
  - Dream 读取尚未处理的 `history.jsonl` 条目。
  - Phase 1 分析新增事实、修正、过时项、重复项和建议编辑。
  - Phase 2 只做最小行级编辑，更新 `USER.md`、`SOUL.md`、`memory/MEMORY.md`。
  - Dream 变更提交到该用户 runtime 目录内的独立 Git 仓库，不污染项目 Git。

## 怎么查看

- 看原始会话：打开 `runtime/ai_assistant_memory/users/<user_id>/sessions/<session_id>.jsonl`。
- 看压缩历史：打开 `runtime/ai_assistant_memory/users/<user_id>/memory/history.jsonl`。
- 看长期记忆：打开 `USER.md`、`SOUL.md`、`memory/MEMORY.md`。
- 看最近 Dream 变化：发送 `/dream-log`。
- 看某次 Dream：发送 `/dream-log <sha>`。

## 怎么回滚

- 发送 `/dream-restore` 列出最近约 10 次 Dream commit。
- 发送 `/dream-restore <sha>` 回滚那次 Dream 变更。
- 回滚本身也会生成一个新的 Dream restore commit，所以可以继续用 Git 追踪。

## 设计边界

- `sessions/*.jsonl` 保留原文，不因为压缩而删除。
- Dream commit body 保存脱敏后的 Phase 1 分析，不保存 raw prompt、密钥、token、完整原始消息或完整简历原文。
- `memory/MEMORY.md` 的 age 标注只注入 Dream prompt，例如 `← 21d`；磁盘文件保持干净。
- 本阶段不做自动 skill 发现/生成。
