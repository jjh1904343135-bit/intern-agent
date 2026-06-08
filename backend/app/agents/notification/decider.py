from __future__ import annotations

from typing import Any

from app.agents.runtime import AgentContext, AgentResult


class NotificationDeciderAgent:
    agent_name = "notification_decider"
    assistant_type = "notification_assistant"

    async def run(self, *, prompt: str, context: AgentContext, **kwargs: Any) -> AgentResult:
        content = await context.provider.generate(prompt, temperature=0.1, max_tokens=500, **kwargs)
        return AgentResult.from_context(context=context, agent_name=self.agent_name, content=content)
