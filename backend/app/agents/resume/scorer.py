from __future__ import annotations

from typing import Any

from app.agents.runtime import AgentContext, AgentResult
from app.prompts import PromptRegistry


class ResumeScoringAgent:
    agent_name = "resume_scorer"
    assistant_type = "resume_assistant"

    async def run(self, *, prompt: str, context: AgentContext, **kwargs: Any) -> AgentResult:
        template = PromptRegistry().load("resume/score")
        content = await context.provider.generate(
            prompt,
            system_prompt=template.system,
            temperature=0.1,
            max_tokens=1600,
            **kwargs,
        )
        return AgentResult.from_context(context=context, agent_name=self.agent_name, content=content)
