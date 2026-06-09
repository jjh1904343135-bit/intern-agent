from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.agents.runtime.base import AgentContext, AgentResult, LLMAgent


class AgentRunner:
    # Keep services coupled to the runner contract, not to a concrete agent.
    async def run(self, agent: LLMAgent, *, prompt: str, context: AgentContext, **kwargs: Any) -> AgentResult:
        return await agent.run(prompt=prompt, context=context, **kwargs)

    async def stream(self, agent: LLMAgent, *, prompt: str, context: AgentContext, **kwargs: Any) -> AsyncIterator[str]:
        async for chunk in agent.stream(prompt=prompt, context=context, **kwargs):
            yield chunk
