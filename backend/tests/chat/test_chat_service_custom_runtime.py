from __future__ import annotations

import pytest

from app.core.settings import settings
from app.services.chat_service import ChatService


class FakeChatRepository:
    def __init__(self) -> None:
        self.db = None
        self.persisted: dict | None = None

    def create(self, **kwargs):
        return type(
            "Session",
            (),
            {
                "id": "session-custom",
                "messages": [],
                "created_at": None,
                "updated_at": None,
                "agent_states": {},
            },
        )()

    def append_turn(self, **kwargs) -> None:
        self.persisted = kwargs


@pytest.mark.asyncio
async def test_chat_service_stream_uses_custom_runtime_without_database() -> None:
    repository = FakeChatRepository()
    service = ChatService(repository)  # type: ignore[arg-type]

    events = [
        event
        async for event in service.stream_events(
            user_id="user-custom",
            message="你好",
            skip_scheduled_task_detection=True,
        )
    ]

    assert events[0]["type"] == "start"
    assert events[-1]["type"] == "end"
    metadata = events[-1]["metadata"]
    assert metadata["agent_runtime"] == "custom"
    assert metadata["context_compression"]["triggered"] is False
    assert metadata["agent_chain"] == ["supervisor", "chat_assistant"]
    assert metadata["agent_pipeline"]["phases"] == [
        "BeforeTurn",
        "BeforeReasoning",
        "PromptRender",
        "Reasoner",
        "AfterReasoning",
        "AfterTurn",
    ]
    assert metadata["intent"] == "simple_answer"
    assert repository.persisted is not None


@pytest.mark.asyncio
async def test_chat_service_custom_runtime_reports_context_compression_without_database(monkeypatch) -> None:
    repository = FakeChatRepository()
    service = ChatService(repository)  # type: ignore[arg-type]

    monkeypatch.setattr("app.core.settings.settings.llm_context_window_tokens", 1200)
    monkeypatch.setattr("app.core.settings.settings.llm_context_reserved_output_tokens", 100)
    long_history = [
        {"role": "user", "content": f"第 {index} 轮" + "很长的历史上下文" * 100}
        for index in range(18)
    ]
    existing_session = type(
        "Session",
        (),
        {
            "id": "session-long-context",
            "messages": long_history,
            "created_at": None,
            "updated_at": None,
            "agent_states": {},
        },
    )()
    repository.create = lambda **kwargs: existing_session  # type: ignore[method-assign]

    events = [
        event
        async for event in service.stream_events(
            user_id="user-custom-long",
            message="继续帮我总结下一步",
            skip_scheduled_task_detection=True,
        )
    ]

    metadata = events[-1]["metadata"]
    assert metadata["agent_runtime"] == "custom"
    assert metadata["context_compression"]["triggered"] is True
    assert metadata["context_compression"]["threshold_ratio"] == 0.5
    assert metadata["context_compression"]["after_tokens"] < metadata["context_compression"]["before_tokens"]
    assert repository.persisted is not None


@pytest.mark.asyncio
async def test_chat_service_intercepts_dream_command_before_scheduled_tasks_and_llm(monkeypatch, tmp_path) -> None:
    repository = FakeChatRepository()
    service = ChatService(repository)  # type: ignore[arg-type]

    monkeypatch.setattr(settings, "ai_assistant_memory_dir", str(tmp_path))

    def fail_scheduled_detection(*args, **kwargs):
        raise AssertionError("slash commands must not enter scheduled task detection")

    monkeypatch.setattr(
        "app.services.scheduled_task_service.ScheduledTaskService.handle_chat_message",
        fail_scheduled_detection,
    )

    events = [
        event
        async for event in service.stream_events(
            user_id="user-custom",
            message="/dream",
            skip_scheduled_task_detection=False,
        )
    ]

    assert events[0]["type"] == "start"
    assert events[-1]["type"] == "end"
    assert "Dream" in events[-1]["full_content"]
    assert events[-1]["metadata"]["intent"] == "memory_command"
    assert repository.persisted is None
