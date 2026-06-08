from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import session_local
from app.core.settings import settings
from app.main import app
from app.models.job import Job
from app.repositories.resume_repository import ResumeRepository

client = TestClient(app)


def _reset_chat_data() -> None:
    with session_local() as session:
        session.execute(text("DELETE FROM assistant_memories"))
        session.execute(text("DELETE FROM chat_sessions"))
        session.execute(text("DELETE FROM interview_sessions"))
        session.execute(text("DELETE FROM applications"))
        session.execute(text("DELETE FROM resumes"))
        session.execute(text("DELETE FROM jobs"))
        session.execute(text("DELETE FROM users"))
        session.commit()


def _auth_headers_with_context() -> dict[str, str]:
    _reset_chat_data()
    register_resp = client.post(
        "/api/v1/auth/register",
        json={"email": "chat@example.com", "password": "Test1234!", "name": "Chat User"},
    )
    data = register_resp.json()["data"]
    token = data["access_token"]
    user_id = data["user_id"]
    with session_local() as session:
        resume_repo = ResumeRepository(session)
        resume = resume_repo.create(
            user_id=user_id,
            file_url="/tmp/chat-resume.pdf",
            file_name="chat-resume.pdf",
            parse_status="done",
        )
        resume.parsed_content = {"summary": "Product and backend intern", "skills": ["Python", "SQL", "Product"]}
        resume.score_report = {
            "overall_score": 82,
            "label": "ready",
            "summary": "Good base resume",
            "dimensions": {"completeness": 80, "skills_depth": 82, "project_quality": 84, "ats_readiness": 81},
            "highlights": ["Clear skills"],
            "risks": ["Add metrics"],
            "next_actions": ["Add metrics"],
            "source": "gemma4",
            "model": "gemma4:26b",
            "status": "ready",
        }
        resume.is_default = True
        session.add(
            Job(
                external_id="chat-job-1",
                source="ashby",
                title="Product Intern",
                company="Notion",
                city="Remote",
                salary_range="$30/hour",
                duration="3 months",
                jd_text="Product analytics SQL user research",
                apply_url="https://jobs.ashbyhq.com/notion/chat-job-1",
                is_active=True,
            )
        )
        session.add(resume)
        session.commit()
    return {"Authorization": f"Bearer {token}"}


def _parse_sse_events(raw_text: str) -> list[dict]:
    events: list[dict] = []
    chunks = [item.strip() for item in raw_text.strip().split("\n\n") if item.strip()]
    for chunk in chunks:
        event_name = None
        data_lines = [line[6:] for line in chunk.splitlines() if line.startswith("data: ")]
        event_lines = [line[7:] for line in chunk.splitlines() if line.startswith("event: ")]
        if event_lines:
            event_name = event_lines[-1]
        if data_lines:
            payload = json.loads("".join(data_lines))
            if event_name and "type" not in payload:
                payload["type"] = event_name
            events.append(payload)
    return events


def test_chat_stream_returns_incremental_start_delta_end_and_persists_history() -> None:
    original_provider = settings.llm_provider
    settings.llm_provider = "mock"
    headers = _auth_headers_with_context()

    try:
        with client.stream(
            "POST",
            "/api/v1/chat/stream",
            headers=headers,
            json={"message": "帮我找产品实习", "session_id": ""},
        ) as response:
            assert response.status_code == 200
            body = "".join(response.iter_text())

        events = _parse_sse_events(body)
        assert events[0]["type"] == "start"
        assert events[-1]["type"] == "end"
        assert [event["type"] for event in events[1:-1]] == ["delta"] * (len(events) - 2)
        assert len(events) >= 4

        session_id = events[-1]["conversation_id"]
        message_id = events[-1]["message_id"]
        deltas = [event["content_delta"] for event in events if event["type"] == "delta"]
        reconstructed = "".join(deltas)

        assert events[0]["conversation_id"] == session_id
        assert all(event["message_id"] == message_id for event in events)
        assert all(event["role"] == "assistant" for event in events)
        assert reconstructed == events[-1]["full_content"]
        assert "MOCK_RESPONSE" in reconstructed
        assert events[-1]["metadata"]["intent"] == "job_search"
        assert events[-1]["metadata"]["source"] == "mock"
        assert events[-1]["metadata"]["request_id"]
        assert events[-1]["metadata"]["agent_run_id"].startswith("chat-")
        assert events[-1]["metadata"]["agent_name"] == "chat_assistant"
        assert events[-1]["metadata"]["agent_chain"] == ["supervisor", "chat_assistant"]
        assert events[-1]["metadata"]["agent_pipeline"]["phases"] == [
            "BeforeTurn",
            "BeforeReasoning",
            "PromptRender",
            "Reasoner",
            "AfterReasoning",
            "AfterTurn",
        ]
        assert "job_search" in events[-1]["metadata"]["eval_tags"]
        assert events[-1]["metadata"]["evidence_summary"]["tool_count"] >= 1
        assert events[-1]["metadata"]["safety_boundary"]["tool_allowlist_enforced"] is True
        assert events[-1]["metadata"]["safety_boundary"]["no_auto_apply"] is True
        actions = events[-1]["metadata"]["suggested_actions"]
        assert actions[0]["kind"] == "job_search"
        assert actions[0]["href"].startswith("/jobs?")
        assert any(action["kind"] == "resume_advice" for action in actions)
        assert any(action["kind"] == "interview_start" for action in actions)

        with session_local() as session:
            rows = session.execute(text("SELECT messages FROM chat_sessions WHERE id = :session_id"), {"session_id": session_id}).scalar_one()
        assert len(rows) == 2
        assert rows[-1]["role"] == "assistant"
        assert rows[-1]["content"] == reconstructed
    finally:
        settings.llm_provider = original_provider


def test_chat_stream_reuses_existing_session_with_agent_memory() -> None:
    original_provider = settings.llm_provider
    settings.llm_provider = "mock"
    headers = _auth_headers_with_context()

    try:
        with client.stream(
            "POST",
            "/api/v1/chat/stream",
            headers=headers,
            json={"message": "第一轮帮我看简历风险", "session_id": ""},
        ) as response:
            first_body = "".join(response.iter_text())
        first_events = _parse_sse_events(first_body)
        session_id = first_events[-1]["conversation_id"]
        assert first_events[-1]["metadata"]["intent"] == "resume_review"
        assert "resume_profile" in first_events[-1]["metadata"]["tools"]

        with client.stream(
            "POST",
            "/api/v1/chat/stream",
            headers=headers,
            json={"message": "第二轮继续给我下一步计划", "session_id": session_id},
        ) as response:
            second_body = "".join(response.iter_text())
        second_events = _parse_sse_events(second_body)
        assert all(event["conversation_id"] == session_id for event in second_events)

        with session_local() as session:
            rows = session.execute(text("SELECT messages FROM chat_sessions WHERE id = :session_id"), {"session_id": session_id}).scalar_one()
            user_id = session.execute(text("SELECT user_id FROM chat_sessions WHERE id = :session_id"), {"session_id": session_id}).scalar_one()
        session_memory_file = (
            Path(settings.ai_assistant_memory_dir)
            / "users"
            / str(user_id)
            / "sessions"
            / f"{session_id}.jsonl"
        )
        memory_lines = [json.loads(line) for line in session_memory_file.read_text(encoding="utf-8").splitlines()]
        assert len(rows) == 4
        assert "第二轮" in rows[-2]["content"]
        assert session_memory_file.exists()
        assert any(item["role"] == "user" and "第二轮" in item["content"] for item in memory_lines)
        assert memory_lines[-1]["role"] == "assistant"
    finally:
        settings.llm_provider = original_provider


def test_chat_sessions_can_be_listed_and_restored_for_current_user() -> None:
    original_provider = settings.llm_provider
    settings.llm_provider = "mock"
    headers = _auth_headers_with_context()

    try:
        with client.stream(
            "POST",
            "/api/v1/chat/stream",
            headers=headers,
            json={"message": "帮我看简历风险", "session_id": ""},
        ) as response:
            first_body = "".join(response.iter_text())
        first_events = _parse_sse_events(first_body)
        session_id = first_events[-1]["conversation_id"]

        list_resp = client.get("/api/v1/chat/sessions", headers=headers)
        assert list_resp.status_code == 200
        list_body = list_resp.json()
        assert list_body["code"] == 0
        assert list_body["data"]["total"] == 1
        assert list_body["data"]["sessions"][0]["session_id"] == session_id
        assert list_body["data"]["sessions"][0]["title"] == "帮我看简历风险"
        assert list_body["data"]["sessions"][0]["message_count"] == 2
        assert list_body["data"]["sessions"][0]["last_question"] == "帮我看简历风险"
        assert list_body["data"]["sessions"][0]["completion"] == "1 turns"
        assert list_body["data"]["sessions"][0]["summary"]
        assert "updated_at" in list_body["data"]["sessions"][0]

        detail_resp = client.get(f"/api/v1/chat/sessions/{session_id}", headers=headers)
        assert detail_resp.status_code == 200
        detail_body = detail_resp.json()
        assert detail_body["code"] == 0
        assert detail_body["data"]["session_id"] == session_id
        assert len(detail_body["data"]["messages"]) == 2
        assert detail_body["data"]["messages"][0]["role"] == "user"
        assert detail_body["data"]["messages"][1]["role"] == "assistant"
    finally:
        settings.llm_provider = original_provider


def test_chat_stream_regenerate_replaces_last_assistant_and_persists_metadata() -> None:
    original_provider = settings.llm_provider
    settings.llm_provider = "mock"
    headers = _auth_headers_with_context()

    try:
        with client.stream(
            "POST",
            "/api/v1/chat/stream",
            headers=headers,
            json={"message": "帮我找产品实习", "session_id": ""},
        ) as response:
            first_body = "".join(response.iter_text())
        first_events = _parse_sse_events(first_body)
        session_id = first_events[-1]["conversation_id"]

        with client.stream(
            "POST",
            "/api/v1/chat/stream",
            headers=headers,
            json={"message": "", "session_id": session_id, "action": "regenerate"},
        ) as response:
            assert response.status_code == 200
            second_body = "".join(response.iter_text())

        events = _parse_sse_events(second_body)
        assert events[0]["type"] == "start"
        assert events[-1]["type"] == "end"
        assert events[-1]["metadata"]["action"] == "regenerate"
        assert events[-1]["metadata"]["provider"] == "mock"
        assert events[-1]["metadata"]["model"] == "mock-local"
        assert events[-1]["metadata"]["delta_count"] >= 1
        assert events[-1]["metadata"]["interrupted"] is False
        assert "total_latency_ms" in events[-1]["metadata"]
        assert "tool_calls_summary" in events[-1]["metadata"]

        with session_local() as session:
            rows = session.execute(text("SELECT messages FROM chat_sessions WHERE id = :session_id"), {"session_id": session_id}).scalar_one()
        assert len(rows) == 2
        assert rows[-2]["role"] == "user"
        assert rows[-1]["role"] == "assistant"
        assert rows[-1]["metadata"]["action"] == "regenerate"
        assert rows[-1]["metadata"]["interrupted"] is False
    finally:
        settings.llm_provider = original_provider


def test_chat_stream_continue_appends_to_last_assistant_message() -> None:
    original_provider = settings.llm_provider
    settings.llm_provider = "mock"
    headers = _auth_headers_with_context()

    try:
        with client.stream(
            "POST",
            "/api/v1/chat/stream",
            headers=headers,
            json={"message": "帮我做求职计划", "session_id": ""},
        ) as response:
            first_body = "".join(response.iter_text())
        first_events = _parse_sse_events(first_body)
        session_id = first_events[-1]["conversation_id"]

        with session_local() as session:
            original_rows = session.execute(text("SELECT messages FROM chat_sessions WHERE id = :session_id"), {"session_id": session_id}).scalar_one()
        original_assistant_content = original_rows[-1]["content"]

        with client.stream(
            "POST",
            "/api/v1/chat/stream",
            headers=headers,
            json={"message": "", "session_id": session_id, "action": "continue"},
        ) as response:
            assert response.status_code == 200
            continue_body = "".join(response.iter_text())

        events = _parse_sse_events(continue_body)
        assert events[-1]["metadata"]["action"] == "continue"

        with session_local() as session:
            rows = session.execute(text("SELECT messages FROM chat_sessions WHERE id = :session_id"), {"session_id": session_id}).scalar_one()
        assert len(rows) == 2
        assert rows[-1]["content"].startswith(original_assistant_content)
        assert len(rows[-1]["content"]) > len(original_assistant_content)
        assert rows[-1]["metadata"]["action"] == "continue"
    finally:
        settings.llm_provider = original_provider


def test_chat_stream_uses_knowledge_search_for_technical_questions(monkeypatch) -> None:
    original_provider = settings.llm_provider
    settings.llm_provider = "mock"
    headers = _auth_headers_with_context()

    class FakeKnowledgeService:
        def __init__(self, db) -> None:
            self.db = db

        def search(self, query: str, *, limit: int = 5, min_score: float = 0.2) -> dict:
            assert "JVM" in query
            return {
                "available": True,
                "query": query,
                "total": 1,
                "source": "knowledge_rag",
                "fallback_notice": None,
                "hits": [
                    {
                        "chunk_id": "chunk-1",
                        "score": 0.89,
                        "text": "JVM 内存区域包含堆、虚拟机栈、本地方法栈、方法区和程序计数器。",
                        "question": "1、 JVM 内存模型是什么",
                        "section_path": ["基础篇", "JVM"],
                        "source_file": "10万字总结.docx",
                        "metadata": {"chunk_index": 0},
                    }
                ],
            }

    monkeypatch.setattr("app.services.chat_service.KnowledgeRagService", FakeKnowledgeService)

    try:
        with client.stream(
            "POST",
            "/api/v1/chat/stream",
            headers=headers,
            json={"message": "讲一下 Java JVM 内存模型", "session_id": ""},
        ) as response:
            assert response.status_code == 200
            body = "".join(response.iter_text())

        events = _parse_sse_events(body)
        metadata = events[-1]["metadata"]
        reconstructed = "".join(event["content_delta"] for event in events if event["type"] == "delta")

        assert "knowledge_search" in metadata["tools"]
        assert any(item["name"] == "knowledge_search" and item["result_count"] == 1 for item in metadata["tool_calls_summary"])
        assert "八股知识库参考" in reconstructed
        assert metadata["knowledge_references"]["count"] == 1
        assert metadata["retrieval_summary"]["knowledge_search"]["result_count"] == 1
        assert metadata["retrieval_summary"]["knowledge_search"]["source"] == "knowledge_rag"
    finally:
        settings.llm_provider = original_provider


def test_chat_stream_metadata_uses_ai_assistant_memory_namespace() -> None:
    original_provider = settings.llm_provider
    settings.llm_provider = "mock"
    headers = _auth_headers_with_context()

    try:
        with client.stream(
            "POST",
            "/api/v1/chat/stream",
            headers=headers,
            json={"message": "帮我找北京 Java 后端实习", "session_id": ""},
        ) as response:
            assert response.status_code == 200
            body = "".join(response.iter_text())

        events = _parse_sse_events(body)
        metadata = events[-1]["metadata"]
        session_id = events[-1]["conversation_id"]

        assert metadata["assistant_type"] == "ai_assistant"
        assert metadata["memory_scope"]["short_term"] == "chat_sessions"
        assert metadata["memory_scope"]["long_term"] == "runtime/ai_assistant_memory"
        assert metadata["memory_updates"]["assistant_type"] == "ai_assistant"
        assert metadata["memory_updates"]["storage"] == "runtime/ai_assistant_memory"
        assert "session" in metadata["memory_updates"]["memory_files"]
        assert metadata["memory_snapshot"]["available"] is True
        assert metadata["memory_snapshot"]["assistant_type"] == "ai_assistant"
        assert metadata["memory_snapshot"]["path"].endswith("/MEMORY.md")
        assert metadata["citation_protocol"]["version"] == "citation_v1"
        assert "interview_assistant" not in json.dumps(metadata["memory_used"], ensure_ascii=False)

        with session_local() as session:
            user_id = session.execute(text("SELECT user_id FROM chat_sessions WHERE id = :session_id"), {"session_id": session_id}).scalar_one()
            ai_count = session.execute(
                text("SELECT count(*) FROM assistant_memories WHERE user_id = :user_id AND assistant_type = 'ai_assistant'"),
                {"user_id": str(user_id)},
            ).scalar_one()
            interview_count = session.execute(
                text("SELECT count(*) FROM assistant_memories WHERE user_id = :user_id AND assistant_type = 'interview_assistant'"),
                {"user_id": str(user_id)},
            ).scalar_one()

        session_memory_file = (
            Path(settings.ai_assistant_memory_dir)
            / "users"
            / str(user_id)
            / "sessions"
            / f"{session_id}.jsonl"
        )
        assert session_memory_file.exists()
        assert ai_count == 0
        assert interview_count == 0
    finally:
        settings.llm_provider = original_provider
