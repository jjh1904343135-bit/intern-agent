from __future__ import annotations

import json
from typing import Any


def chunk_text(text: str, *, size: int = 18) -> list[str]:
    """Split completed provider output into small chunks when native streaming is unavailable."""
    if not text:
        return []
    return [text[index : index + size] for index in range(0, len(text), size)]


def stream_event(
    event_type: str,
    *,
    conversation_id: str,
    role: str = "assistant",
    message_id: str,
    **payload: Any,
) -> dict[str, Any]:
    return {
        "type": event_type,
        "conversation_id": conversation_id,
        "role": role,
        "message_id": message_id,
        **payload,
    }


def encode_sse_event(event: dict[str, Any]) -> str:
    event_name = str(event.get("type") or "message")
    return f"event: {event_name}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

