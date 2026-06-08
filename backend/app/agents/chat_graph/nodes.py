from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from app.agents.chat import ChatAssistantAgent
from app.agents.chat.complexity import AGENTIC_TASK, ChatComplexityClassifier
from app.agents.chat_graph.context import maybe_compress_context
from app.agents.chat_graph.state import ChatGraphState
from app.agents.runtime import AgentContext, AgentRunner
from app.agents.supervisor import SupervisorTurn
from app.prompts import PromptRegistry
from app.services.chat_output_format import format_assistant_plain_text


def load_memory_node(state: ChatGraphState, config: RunnableConfig) -> dict[str, Any]:
    dependencies = _dependencies(config)
    file_memory_context = dependencies.file_memory_service.read_context(
        user_id=state["user_id"],
        session_id=state["session_id"],
    )
    memory_context = dependencies.file_memory_service.public_context_metadata(file_memory_context)
    return {"file_memory_context": file_memory_context, "memory_context": memory_context}


def route_complexity_node(state: ChatGraphState, config: RunnableConfig) -> dict[str, Any]:
    return {"complexity": ChatComplexityClassifier().classify(state["message"])}


def plan_node(state: ChatGraphState, config: RunnableConfig) -> dict[str, Any]:
    dependencies = _dependencies(config)
    if state.get("complexity") == AGENTIC_TASK:
        turn = dependencies.supervisor.plan_turn(message=state["message"], history=state.get("history") or [], tool_context={})
    else:
        turn = _simple_turn(
            supervisor=dependencies.supervisor,
            message=state["message"],
            history=state.get("history") or [],
            file_memory_context=state.get("file_memory_context") or {},
        )
    return {"base_turn": turn, "turn": turn}


def run_tools_node(state: ChatGraphState, config: RunnableConfig) -> dict[str, Any]:
    dependencies = _dependencies(config)
    turn = state["turn"]
    tool_context = dependencies.run_tools(
        user_id=state["user_id"],
        intent=turn.intent,
        message=state["message"],
        tools=turn.tools,
    )
    tool_context["assistant_memory"] = state.get("memory_context") or {}
    tool_context["assistant_file_memory"] = {"content": (state.get("file_memory_context") or {}).get("summary_text", "")}
    return {"tool_context": tool_context}


def compress_context_node(state: ChatGraphState, config: RunnableConfig) -> dict[str, Any]:
    dependencies = _dependencies(config)
    turn = state["turn"]
    compression = maybe_compress_context(
        history=state.get("history") or [],
        file_memory_context=state.get("file_memory_context") or {},
        tool_context=state.get("tool_context") or {},
        prompt=turn.prompt,
        budget=dependencies.context_budget,
    )
    updates: dict[str, Any] = {"compression": _compression_metadata(compression)}
    if compression.get("triggered"):
        updates["history"] = compression["history"]
        updates["file_memory_context"] = compression["file_memory_context"]
    return updates


def render_prompt_node(state: ChatGraphState, config: RunnableConfig) -> dict[str, Any]:
    dependencies = _dependencies(config)
    if state.get("complexity") == AGENTIC_TASK:
        tool_context = dict(state.get("tool_context") or {})
        if memory_snapshot_content := _memory_snapshot_content(state):
            tool_context["assistant_memory_snapshot"] = {"content": memory_snapshot_content}
        turn = dependencies.supervisor.plan_turn(
            message=state["message"],
            history=state.get("history") or [],
            tool_context=tool_context,
        )
        return {"turn": turn, "tool_context": tool_context}
    return {"turn": state["turn"]}


async def reasoner_node(state: ChatGraphState, config: RunnableConfig) -> dict[str, Any]:
    dependencies = _dependencies(config)
    assistant_agent = ChatAssistantAgent()
    agent_context = AgentContext(
        provider=dependencies.provider,
        request_id=dependencies.request_id,
        assistant_type="ai_assistant",
    )
    result = await AgentRunner().run(
        assistant_agent,
        prompt=state["turn"].prompt,
        context=agent_context,
        system_prompt=state["turn"].system_prompt,
        temperature=0.2,
        max_tokens=700,
    )
    return {
        "final_text": format_assistant_plain_text(result.content),
        "metadata_patch": {
            "agent_name": assistant_agent.agent_name,
            "model": dependencies.provider.model,
            "provider": dependencies.provider.name,
        },
    }


def _simple_turn(*, supervisor, message: str, history: list[dict[str, Any]], file_memory_context: dict[str, Any]) -> SupervisorTurn:
    rendered = PromptRegistry().render(
        "chat/simple_answer",
        {
            "message": message,
            "history_text": supervisor._history_to_text(history),
            "memory_text": str(file_memory_context.get("summary_text") or "")[:1600],
        },
    )
    return SupervisorTurn(
        agent_name=supervisor.agent_name,
        intent="simple_answer",
        focus="simple_answer",
        steps=["direct_answer"],
        tools=[],
        system_prompt=rendered.system,
        prompt=rendered.user,
        prompt_template_id=rendered.template_id,
        prompt_template_version=rendered.version,
    )


def _compression_metadata(compression: dict[str, Any]) -> dict[str, Any]:
    return {
        "triggered": bool(compression.get("triggered")),
        "threshold_ratio": compression.get("threshold_ratio"),
        "threshold_tokens": compression.get("threshold_tokens"),
        "before_tokens": compression.get("before_tokens"),
        "after_tokens": compression.get("after_tokens"),
        "summary": compression.get("summary", ""),
    }


def _memory_snapshot_content(state: ChatGraphState) -> str:
    file_memory_context = state.get("file_memory_context") or {}
    return str(file_memory_context.get("MEMORY.md") or "")[:1600]


def _dependencies(config: RunnableConfig):
    configurable = config.get("configurable") or {}
    dependencies = configurable.get("dependencies")
    if dependencies is None:
        raise RuntimeError("chat graph dependencies missing")
    return dependencies
