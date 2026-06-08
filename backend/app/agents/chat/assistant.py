from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.agents.runtime import AgentContext, AgentResult


class ChatAssistantAgent:
    agent_name = "chat_assistant"
    assistant_type = "ai_assistant"

    # 这个 Agent 本身不做业务决策，只把已经渲染好的 Prompt 交给 Provider 生成文本。
    async def run(self, *, prompt: str, context: AgentContext, **kwargs: Any) -> AgentResult:
        content = await context.provider.generate(prompt, **kwargs)
        return AgentResult.from_context(context=context, agent_name=self.agent_name, content=content)

    async def stream(self, *, prompt: str, context: AgentContext, **kwargs: Any) -> AsyncIterator[str]:
        async for chunk in context.provider.stream_generate(prompt, **kwargs):
            yield chunk
