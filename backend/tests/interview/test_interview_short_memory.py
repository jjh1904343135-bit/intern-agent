from __future__ import annotations

from app.services.interview_service import InterviewService


def test_interview_memory_scope_is_current_session_only() -> None:
    scope = InterviewService._interview_memory_scope()

    assert scope["short_term"] == "interview_sessions.report.agent_state"
    assert scope["long_term"] is None
    assert scope["compression"] == "agent_state.session_summary"


def test_interview_memory_updates_do_not_write_long_term_repository(monkeypatch) -> None:
    class FailingRepository:
        def __init__(self, db) -> None:
            self.db = db

        def upsert(self, **kwargs):  # pragma: no cover - should never be called
            raise AssertionError("interview assistant must not write long-term assistant_memories")

    monkeypatch.setattr("app.services.interview_service.AssistantMemoryRepository", FailingRepository)
    service = InterviewService(interview_repository=None, job_repository=None, resume_repository=None)  # type: ignore[arg-type]

    result = service._remember_interview_turn(
        user_id="user-1",
        session=type("Session", (), {"id": "s1", "job_id": "j1", "resume_id": "r1"})(),
        next_status="summary",
        agent_update={"agent_state": {"difficulty": 3}},
        job=None,
    )

    assert result["assistant_type"] == "interview_assistant"
    assert result["count"] == 0
    assert result["storage"] == "interview_sessions.report.agent_state"


def test_interview_agent_state_soft_compression_keeps_session_summary() -> None:
    agent_state = {
        "asked_questions": [
            {"question_id": f"q-{index}", "answer": "很长的回答" * 80, "signals": {"depth": 0.5}}
            for index in range(5)
        ],
        "evaluation_state": {"technical_depth": 3},
    }

    compacted = InterviewService._soft_compress_agent_state(agent_state)

    assert compacted["session_summary"]["compressed_round_count"] >= 1
    assert "q-0" in compacted["session_summary"]["summary"]
    assert len(str(compacted["asked_questions"][0].get("answer", ""))) < 260
