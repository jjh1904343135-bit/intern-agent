from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from app.core.providers.base import LLMProvider
from app.agents.runtime import AgentContext, AgentResult, AgentRunner, LLMAgent


class FakeProvider(LLMProvider):
    name = "fake"
    model = "fake-model"

    async def generate(self, prompt: str, **kwargs) -> str:
        return f"generated:{prompt}:{kwargs.get('system_prompt', '')}"

    async def stream_generate(self, prompt: str, **kwargs) -> AsyncIterator[str]:
        yield "stream:"
        yield prompt


class EchoAgent(LLMAgent):
    agent_name = "echo_agent"
    assistant_type = "ai_assistant"

    async def run(self, *, prompt: str, context: AgentContext, **kwargs) -> AgentResult:
        content = await context.provider.generate(prompt, **kwargs)
        return AgentResult.from_context(
            context=context,
            agent_name=self.agent_name,
            content=content,
            metadata={"prompt_length": len(prompt)},
        )

    async def stream(self, *, prompt: str, context: AgentContext, **kwargs) -> AsyncIterator[str]:
        async for chunk in context.provider.stream_generate(prompt, **kwargs):
            yield chunk


@pytest.mark.asyncio
async def test_agent_runner_returns_standard_metadata() -> None:
    context = AgentContext(
        provider=FakeProvider(),
        request_id="req-agent-test",
        assistant_type="ai_assistant",
    )

    result = await AgentRunner().run(EchoAgent(), prompt="hello", context=context, system_prompt="system")

    assert result.content == "generated:hello:system"
    assert result.agent_name == "echo_agent"
    assert result.assistant_type == "ai_assistant"
    assert result.provider == "fake"
    assert result.model == "fake-model"
    assert result.metadata["prompt_length"] == 5
    assert result.to_metadata() == {
        "agent_name": "echo_agent",
        "assistant_type": "ai_assistant",
        "provider": "fake",
        "model": "fake-model",
        "prompt_length": 5,
    }


@pytest.mark.asyncio
async def test_agent_runner_streams_chunks_and_keeps_result_metadata() -> None:
    context = AgentContext(
        provider=FakeProvider(),
        request_id="req-agent-test",
        assistant_type="ai_assistant",
    )

    chunks: list[str] = []
    async for chunk in AgentRunner().stream(EchoAgent(), prompt="hello", context=context):
        chunks.append(chunk)

    assert chunks == ["stream:", "hello"]
