from __future__ import annotations

import pytest

from app.agents.runtime.lifecycle import AgentLifecycleRecorder, AgentPipelineError


def test_agent_lifecycle_recorder_keeps_canonical_phase_order() -> None:
    recorder = AgentLifecycleRecorder(
        assistant_type="ai_assistant",
        request_id="req-test",
        agent_run_id="chat-test",
    )

    recorder.complete("BeforeTurn", session_id="session-1")
    recorder.complete("BeforeReasoning", intent="job_search", tools=["resume_profile", "job_search"])
    recorder.complete("PromptRender", prompt_chars=1200)
    recorder.complete("Reasoner", provider="mock", model="mock-local")
    recorder.complete("AfterReasoning", status="ready", delta_count=3)
    recorder.complete("AfterTurn", memory_updates={"confirmed_count": 1})

    summary = recorder.summary()

    assert summary["name"] == "chat_agent_pipeline"
    assert summary["assistant_type"] == "ai_assistant"
    assert summary["request_id"] == "req-test"
    assert summary["agent_run_id"] == "chat-test"
    assert summary["phases"] == [
        "BeforeTurn",
        "BeforeReasoning",
        "PromptRender",
        "Reasoner",
        "AfterReasoning",
        "AfterTurn",
    ]
    assert summary["steps"][1]["summary"]["intent"] == "job_search"


def test_agent_lifecycle_recorder_rejects_out_of_order_phase() -> None:
    recorder = AgentLifecycleRecorder(
        assistant_type="ai_assistant",
        request_id="req-test",
        agent_run_id="chat-test",
    )

    recorder.complete("BeforeTurn")

    with pytest.raises(AgentPipelineError):
        recorder.complete("Reasoner")
