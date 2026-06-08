from __future__ import annotations

from typing import Any, TypedDict

from app.agents.supervisor import SupervisorTurn


class ChatGraphState(TypedDict, total=False):
    user_id: str
    session_id: str
    message: str
    action: str
    history: list[dict[str, Any]]
    complexity: str
    file_memory_context: dict[str, Any]
    memory_context: dict[str, Any]
    base_turn: SupervisorTurn
    tool_context: dict[str, Any]
    turn: SupervisorTurn
    final_text: str
    raw_parts: list[str]
    metadata_patch: dict[str, Any]
    context_budget: dict[str, Any]
    compression: dict[str, Any]
