from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.agents.chat.complexity import AGENTIC_TASK
from app.agents.chat_graph.nodes import (
    compress_context_node,
    load_memory_node,
    plan_node,
    reasoner_node,
    render_prompt_node,
    route_complexity_node,
    run_tools_node,
)
from app.agents.chat_graph.state import ChatGraphState

CHAT_GRAPH_NODE_NAMES = [
    "load_memory",
    "route_complexity",
    "plan",
    "run_tools",
    "compress_context",
    "render_prompt",
    "reasoner",
]


def chat_graph_node_names() -> list[str]:
    return list(CHAT_GRAPH_NODE_NAMES)


def build_chat_graph():
    graph = StateGraph(ChatGraphState)
    graph.add_node("load_memory", load_memory_node)
    graph.add_node("route_complexity", route_complexity_node)
    graph.add_node("plan", plan_node)
    graph.add_node("run_tools", run_tools_node)
    graph.add_node("compress_context", compress_context_node)
    graph.add_node("render_prompt", render_prompt_node)
    graph.add_node("reasoner", reasoner_node)

    graph.set_entry_point("load_memory")
    graph.add_edge("load_memory", "route_complexity")
    graph.add_edge("route_complexity", "plan")
    graph.add_conditional_edges("plan", _tool_route, {"run_tools": "run_tools", "compress_context": "compress_context"})
    graph.add_edge("run_tools", "compress_context")
    graph.add_edge("compress_context", "render_prompt")
    graph.add_edge("render_prompt", "reasoner")
    graph.add_edge("reasoner", END)
    return graph.compile()


def _tool_route(state: ChatGraphState) -> str:
    return "run_tools" if state.get("complexity") == AGENTIC_TASK else "compress_context"
