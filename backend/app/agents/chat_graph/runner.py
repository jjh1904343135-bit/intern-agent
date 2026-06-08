from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.agents.chat_graph.context import ChatContextBudget
from app.agents.chat_graph.state import ChatGraphState
from app.agents.chat_graph.workflow import build_chat_graph
from app.agents.supervisor import SupervisorAgent, SupervisorTurn
from app.core.providers.base import LLMProvider
from app.core.settings import settings
from app.services.ai_assistant_file_memory import AIMemoryFileService


@dataclass
class ChatGraphDependencies:
    provider: LLMProvider
    supervisor: SupervisorAgent
    file_memory_service: AIMemoryFileService
    run_tools: Callable[..., dict[str, Any]]
    request_id: str
    context_budget: ChatContextBudget = field(default_factory=lambda: ChatContextBudget(
        context_window_tokens=settings.llm_context_window_tokens,
        compression_ratio=settings.llm_context_compression_ratio,
        reserved_output_tokens=settings.llm_context_reserved_output_tokens,
    ))


@dataclass(frozen=True)
class ChatGraphResult:
    turn: SupervisorTurn
    final_text: str
    tool_context: dict[str, Any]
    memory_context: dict[str, Any]
    file_memory_context: dict[str, Any]
    compression: dict[str, Any]
    metadata_patch: dict[str, Any]
    agent_chain: list[str]


class ChatGraphRunner:
    def __init__(self, *, dependencies: ChatGraphDependencies) -> None:
        self.dependencies = dependencies
        self.graph = build_chat_graph()

    async def run(
        self,
        *,
        user_id: str,
        session_id: str,
        message: str,
        action: str,
        history: list[dict[str, Any]],
    ) -> ChatGraphResult:
        initial_state: ChatGraphState = {
            "user_id": user_id,
            "session_id": session_id,
            "message": message,
            "action": action,
            "history": history,
            "tool_context": {},
            "raw_parts": [],
        }
        final_state = await self.graph.ainvoke(initial_state, config={"configurable": {"dependencies": self.dependencies}})
        turn = final_state["turn"]
        agent_chain = [self.dependencies.supervisor.agent_name, "chat_assistant"]
        metadata_patch = {
            **final_state.get("metadata_patch", {}),
            "agent_runtime": "langgraph",
            "agent_chain": agent_chain,
            "prompt_template_id": turn.prompt_template_id,
            "prompt_template_version": turn.prompt_template_version,
            "context_compression": final_state.get("compression", {}),
        }
        return ChatGraphResult(
            turn=turn,
            final_text=str(final_state.get("final_text") or ""),
            tool_context=dict(final_state.get("tool_context") or {}),
            memory_context=dict(final_state.get("memory_context") or {}),
            file_memory_context=dict(final_state.get("file_memory_context") or {}),
            compression=dict(final_state.get("compression") or {}),
            metadata_patch=metadata_patch,
            agent_chain=agent_chain,
        )
