from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.core.providers.base import LLMProvider


@dataclass(frozen=True)
class AgentContext:
    # Per-call context shared by the agent, provider, and tracing layer.
    provider: LLMProvider
    request_id: str
    assistant_type: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentResult:
    content: str
    agent_name: str
    assistant_type: str
    provider: str
    model: str | None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_context(
        cls,
        *,
        context: AgentContext,
        agent_name: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> "AgentResult":
        return cls(
            content=content,
            agent_name=agent_name,
            assistant_type=context.assistant_type,
            provider=context.provider.name,
            model=context.provider.model,
            metadata=metadata or {},
        )

    def to_metadata(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "assistant_type": self.assistant_type,
            "provider": self.provider,
            "model": self.model,
            **self.metadata,
        }


class LLMAgent(Protocol):
    agent_name: str
    assistant_type: str

    async def run(self, *, prompt: str, context: AgentContext, **kwargs: Any) -> AgentResult:
        raise NotImplementedError

    async def stream(self, *, prompt: str, context: AgentContext, **kwargs: Any) -> AsyncIterator[str]:
        raise NotImplementedError
