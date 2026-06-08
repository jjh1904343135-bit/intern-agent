from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.agents.runtime import AgentContext, AgentResult
from app.prompts import PromptRegistry


class InterviewFeedbackAgent:
    agent_name = "interview_feedback"
    assistant_type = "interview_assistant"

    async def run(self, *, prompt: str, context: AgentContext, **kwargs: Any) -> AgentResult:
        system_prompt = PromptRegistry().load("interview/feedback").system
        content = await context.provider.generate(
            prompt,
            system_prompt=system_prompt,
            temperature=0.2,
            max_tokens=500,
            **kwargs,
        )
        return AgentResult.from_context(context=context, agent_name=self.agent_name, content=content)

    async def stream(self, *, prompt: str, context: AgentContext, **kwargs: Any) -> AsyncIterator[str]:
        system_prompt = PromptRegistry().load("interview/feedback").system
        async for chunk in context.provider.stream_generate(
            prompt,
            system_prompt=system_prompt,
            temperature=0.2,
            max_tokens=500,
            **kwargs,
        ):
            yield chunk
