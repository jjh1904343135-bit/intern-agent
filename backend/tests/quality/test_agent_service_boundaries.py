from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_chat_tool_executor_lives_in_service_layer() -> None:
    assert not (PROJECT_ROOT / "app" / "agents" / "chat" / "tools.py").exists()
    assert (PROJECT_ROOT / "app" / "services" / "chat_tool_service.py").exists()
