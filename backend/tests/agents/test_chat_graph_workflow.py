from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from app.agents.chat_graph import ChatGraphDependencies, ChatGraphRunner, build_chat_graph, chat_graph_node_names
from app.agents.supervisor import SupervisorAgent
from app.core.providers.base import LLMProvider
from app.services.ai_assistant_file_memory import AIMemoryFileService


class FakeProvider(LLMProvider):
    @property
    def name(self) -> str:
        return "fake"

    @property
    def model(self) -> str:
        return "fake-model"

    @property
    def supports_stream(self) -> bool:
        return True

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        return f"generated:{prompt[:80]}"

    async def stream_generate(self, prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        yield await self.generate(prompt, **kwargs)


@pytest.mark.asyncio
async def test_chat_graph_routes_simple_answer_without_tools(tmp_path: Path) -> None:
    calls: list[str] = []

    def run_tools(**kwargs: Any) -> dict[str, Any]:
        calls.append("called")
        return {}

    dependencies = ChatGraphDependencies(
        provider=FakeProvider(),
        supervisor=SupervisorAgent(),
        file_memory_service=AIMemoryFileService(root=tmp_path),
        run_tools=run_tools,
        request_id="req-graph-test",
    )

    result = await ChatGraphRunner(dependencies=dependencies).run(
        user_id="user-1",
        session_id="session-1",
        message="你好",
        action="send",
        history=[],
    )

    assert calls == []
    assert result.turn.intent == "simple_answer"
    assert result.turn.tools == []
    assert result.agent_chain == ["supervisor", "chat_assistant"]
    assert result.metadata_patch["agent_runtime"] == "langgraph"
    assert result.metadata_patch["prompt_template_id"] == "chat/simple_answer"
    assert result.final_text.startswith("generated:")


@pytest.mark.asyncio
async def test_chat_graph_routes_agentic_task_through_tools_and_supervisor(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def run_tools(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"job_search": {"total": 1, "top_titles": ["美团 后端"]}}

    dependencies = ChatGraphDependencies(
        provider=FakeProvider(),
        supervisor=SupervisorAgent(),
        file_memory_service=AIMemoryFileService(root=tmp_path),
        run_tools=run_tools,
        request_id="req-graph-test",
    )

    result = await ChatGraphRunner(dependencies=dependencies).run(
        user_id="user-1",
        session_id="session-1",
        message="帮我搜一下美团开发岗",
        action="send",
        history=[],
    )

    assert captured["intent"] == "job_search"
    assert "job_search" in captured["tools"]
    assert result.turn.intent == "job_search"
    assert "job_search" in result.turn.tools
    assert result.tool_context["job_search"]["total"] == 1
    assert result.metadata_patch["context_compression"]["triggered"] is False
    assert result.metadata_patch["agent_chain"] == ["supervisor", "chat_assistant"]


def test_chat_graph_declares_expected_node_names() -> None:
    graph = build_chat_graph()

    assert graph is not None
    assert chat_graph_node_names() == [
        "load_memory",
        "route_complexity",
        "plan",
        "run_tools",
        "compress_context",
        "render_prompt",
        "reasoner",
    ]
