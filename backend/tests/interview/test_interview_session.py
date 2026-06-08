from __future__ import annotations

import json

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import session_local
from app.core.settings import settings
from app.main import app
from app.models.job import Job
from app.repositories.resume_repository import ResumeRepository

client = TestClient(app)


def _reset_interview_data() -> None:
    with session_local() as session:
        session.execute(text("DELETE FROM assistant_memories"))
        session.execute(text("DELETE FROM chat_sessions"))
        session.execute(text("DELETE FROM interview_sessions"))
        session.execute(text("DELETE FROM applications"))
        session.execute(text("DELETE FROM resumes"))
        session.execute(text("DELETE FROM jobs"))
        session.execute(text("DELETE FROM users"))
        session.commit()


def _prepare_user_and_job(
    *,
    with_resume: bool = True,
    title: str = "AI Backend Intern",
    jd_text: str = "FastAPI Python SQL Redis",
    parsed_resume: dict | None = None,
) -> tuple[dict[str, str], str, str | None]:
    _reset_interview_data()
    register_resp = client.post(
        "/api/v1/auth/register",
        json={"email": "interview@example.com", "password": "Test1234!", "name": "面试用户"},
    )
    register_data = register_resp.json()["data"]
    token = register_data["access_token"]
    user_id = register_data["user_id"]
    headers = {"Authorization": f"Bearer {token}"}

    with session_local() as session:
        session.add(
            Job(
                external_id="job-day7-001",
                source="manual",
                title=title,
                company="InternAgent",
                city="Shanghai",
                salary_range="250/day",
                duration="3 months",
                jd_text=jd_text,
                apply_url="https://example.com/jobs/day7",
                is_active=True,
            )
        )
        session.commit()
        resume_id = None
        if with_resume:
            resume_repo = ResumeRepository(session)
            resume = resume_repo.create(
                user_id=user_id,
                file_url="/tmp/interview-resume.docx",
                file_name="interview-resume.docx",
                parse_status="done",
            )
            resume_repo.mark_done(
                resume=resume,
                parsed_content=parsed_resume
                or {
                    "summary": "候选人有 FastAPI、SQL、Redis 和异步任务项目经验。",
                    "skills": ["FastAPI", "Python", "SQL", "Redis", "TDD"],
                    "projects": [{"name": "InternAgent", "impact": "完成求职闭环"}],
                },
                score_report={"overall_score": 84, "status": "ready", "model": "gemma4:26b"},
            )
            resume_id = str(resume.id)
        job = session.query(Job).filter(Job.external_id == "job-day7-001").one()
        return headers, str(job.id), resume_id


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


def test_interview_session_start_answer_and_report_flow() -> None:
    original_provider = settings.llm_provider
    settings.llm_provider = "mock"
    headers, job_id, resume_id = _prepare_user_and_job()

    try:
        start_resp = client.post(
            "/api/v1/interview/session/start",
            headers=headers,
            json={"job_id": job_id, "mode": "standard"},
        )
        assert start_resp.status_code == 201
        start_body = start_resp.json()
        assert start_body["code"] == 0
        assert start_body["data"]["mode"] == "standard"
        assert start_body["data"]["resume_id"] == resume_id
        assert start_body["data"]["resume_file_name"] == "interview-resume.docx"
        assert start_body["data"]["messages"][0]["role"] == "assistant"
        assert "FastAPI" in start_body["data"]["messages"][0]["content"]
        assert "InternAgent" in start_body["data"]["messages"][0]["content"]
        assert "接口" in start_body["data"]["messages"][0]["content"]

        session_id = start_body["data"]["session_id"]
        answer_resp = client.post(
            f"/api/v1/interview/session/{session_id}/answer",
            headers=headers,
            json={"answer": "我会先澄清需求，再拆分接口、数据库和异步任务，最后补测试和监控。"},
        )
        assert answer_resp.status_code == 200
        answer_body = answer_resp.json()
        assert answer_body["code"] == 0
        assert answer_body["data"]["messages"][-2]["role"] == "user"
        assert answer_body["data"]["messages"][-1]["role"] == "assistant"
        assert answer_body["data"]["messages"][-1]["feedback_score"] >= 1

        detail_resp = client.get(f"/api/v1/interview/session/{session_id}", headers=headers)
        assert detail_resp.status_code == 200
        detail_body = detail_resp.json()
        assert detail_body["code"] == 0
        assert detail_body["data"]["session_id"] == session_id
        assert len(detail_body["data"]["messages"]) >= 3

        report_resp = client.get(f"/api/v1/interview/session/{session_id}/report", headers=headers)
        assert report_resp.status_code == 200
        report_body = report_resp.json()
        assert report_body["code"] == 0
        assert report_body["data"]["overall_score"] >= 1
        assert "communication" in report_body["data"]["dimensions"]
        assert report_body["data"]["session_id"] == session_id
    finally:
        settings.llm_provider = original_provider


def test_interview_start_builds_agent_state_from_job_and_resume_intersection() -> None:
    original_provider = settings.llm_provider
    settings.llm_provider = "mock"
    headers, job_id, resume_id = _prepare_user_and_job(
        title="AI Agent 工程师实习生",
        jd_text="负责 LLM Agent、RAG 检索、Python 后端工程化、Qdrant 向量库和评测体系建设。",
        parsed_resume={
            "summary": "做过 InternAgent 求职项目，包含 RAG 岗位检索、Qdrant、FastAPI、Docker 和 pytest。",
            "skills": ["Python", "FastAPI", "Qdrant", "RAG", "Docker", "pytest"],
            "projects": [
                {
                    "name": "InternAgent",
                    "description": "基于 FastAPI、Qdrant 和 Gemma4 构建岗位检索、简历解析和面试训练闭环。",
                    "impact": "完成 Docker 化、TDD 和流式 SSE。",
                }
            ],
            "experience": [],
            "education": [],
        },
    )

    try:
        start_resp = client.post(
            "/api/v1/interview/session/start",
            headers=headers,
            json={"job_id": job_id, "mode": "standard"},
        )

        assert start_resp.status_code == 201
        data = start_resp.json()["data"]
        agent_state = data["agent_state"]
        assert agent_state["job_profile"]["title"] == "AI Agent 工程师实习生"
        assert agent_state["job_profile"]["level"] == "intern"
        assert {"LLM", "RAG"}.issubset(set(agent_state["job_profile"]["domain_tags"]))
        assert {"Python", "Qdrant", "RAG"}.issubset(set(agent_state["candidate_profile"]["skills"]))
        assert {"Python", "Qdrant", "RAG"}.intersection(set(agent_state["candidate_profile"]["matched_skills"]))
        assert agent_state["question_plan"][0]["category"] == "experience"
        assert "InternAgent" in agent_state["question_plan"][0]["prompt"]
        assert "RAG" in agent_state["question_plan"][0]["prompt"]
        assert data["messages"][0]["question_id"] == agent_state["question_plan"][0]["id"]
        assert data["messages"][0]["content"] == agent_state["question_plan"][0]["prompt"]

        detail_resp = client.get(f"/api/v1/interview/session/{data['session_id']}", headers=headers)
        report_state = detail_resp.json()["data"]["report"]["agent_state"]
        assert report_state["session_id"] == data["session_id"]
        assert report_state["candidate_profile"]["resume_id"] == resume_id
    finally:
        settings.llm_provider = original_provider


def test_interview_stream_updates_agent_signals_scores_difficulty_and_followup_strategy() -> None:
    original_provider = settings.llm_provider
    settings.llm_provider = "mock"
    headers, job_id, _resume_id = _prepare_user_and_job(
        title="AI Agent 工程师实习生",
        jd_text="负责 LLM Agent、RAG 检索、Python 后端工程化、Qdrant 向量库和评测体系建设。",
        parsed_resume={
            "summary": "做过 InternAgent 求职项目，包含 RAG 岗位检索、Qdrant、FastAPI、Docker 和 pytest。",
            "skills": ["Python", "FastAPI", "Qdrant", "RAG", "Docker", "pytest"],
            "projects": [{"name": "InternAgent", "description": "RAG、Qdrant、FastAPI、SSE、TDD"}],
            "experience": [],
            "education": [],
        },
    )

    try:
        start_resp = client.post(
            "/api/v1/interview/session/start",
            headers=headers,
            json={"job_id": job_id, "mode": "standard"},
        )
        session_id = start_resp.json()["data"]["session_id"]
        start_difficulty = start_resp.json()["data"]["agent_state"]["difficulty"]

        with client.stream(
            "POST",
            f"/api/v1/interview/session/{session_id}/answer/stream",
            headers=headers,
            json={
                "answer": (
                    "我在 InternAgent 里负责 RAG 岗位检索，用 FastAPI 拆分接口，"
                    "用 Qdrant 存岗位向量，补了 pytest 回归测试，并用 Docker Compose 跑完整链路。"
                    "遇到召回慢时我会先看 embedding 和过滤条件，再补缓存和重建索引。"
                )
            },
        ) as response:
            assert response.status_code == 200
            body = "".join(response.iter_text())

        events = _parse_sse_events(body)
        end_metadata = events[-1]["metadata"]
        assert end_metadata["agent"]["answer_signals"]["specificity"] >= 4
        assert "RAG" in end_metadata["agent"]["answer_signals"]["mentioned_skills"]
        assert end_metadata["agent"]["evaluation_state"]["technical_depth"] >= 3
        assert end_metadata["agent"]["difficulty"] >= start_difficulty
        assert end_metadata["agent"]["followup_strategy"] in {"clarify", "drill_down", "challenge", "transfer"}
        assert end_metadata["request_id"]
        assert end_metadata["agent_run_id"].startswith("interview-")
        assert end_metadata["agent_name"] == "interview_feedback"
        assert end_metadata["agent_chain"] == ["interview_feedback"]
        assert "interview_assistant" in end_metadata["eval_tags"]
        assert end_metadata["evidence_summary"]["answer_signals"]["specificity"] >= 4
        assert end_metadata["safety_boundary"]["context_isolated"] is True

        detail_resp = client.get(f"/api/v1/interview/session/{session_id}", headers=headers)
        agent_state = detail_resp.json()["data"]["report"]["agent_state"]
        assert agent_state["asked_questions"][0]["answer_signals"]["specificity"] >= 4
        assert agent_state["evaluation_state"]["technical_depth"] >= 3
        assert agent_state["difficulty"] >= start_difficulty
        assert agent_state["last_followup_strategy"] == end_metadata["agent"]["followup_strategy"]
    finally:
        settings.llm_provider = original_provider


def test_interview_answer_stream_returns_incremental_contract_and_persists_message() -> None:
    original_provider = settings.llm_provider
    settings.llm_provider = "mock"
    headers, job_id, _resume_id = _prepare_user_and_job()

    try:
        start_resp = client.post(
            "/api/v1/interview/session/start",
            headers=headers,
            json={"job_id": job_id, "mode": "standard"},
        )
        session_id = start_resp.json()["data"]["session_id"]

        with client.stream(
            "POST",
            f"/api/v1/interview/session/{session_id}/answer/stream",
            headers=headers,
            json={"answer": "我会先澄清需求，再用 STAR 讲项目背景、行动和结果，并说明复盘。"},
        ) as response:
            assert response.status_code == 200
            body = "".join(response.iter_text())

        events = _parse_sse_events(body)
        assert events[0]["type"] == "start"
        assert events[-1]["type"] == "end"
        assert [event["type"] for event in events[1:-1]] == ["delta"] * (len(events) - 2)
        assert len(events) >= 4

        deltas = [event["content_delta"] for event in events if event["type"] == "delta"]
        reconstructed = "".join(deltas)
        assert events[-1]["conversation_id"] == session_id
        assert events[-1]["full_content"] == reconstructed
        assert events[-1]["metadata"]["mode"] == "standard"
        assert events[-1]["metadata"]["source"] == "mock"
        assert events[-1]["metadata"]["feedback_score"] >= 1

        detail_resp = client.get(f"/api/v1/interview/session/{session_id}", headers=headers)
        messages = detail_resp.json()["data"]["messages"]
        assert messages[-2]["role"] == "user"
        assert messages[-1]["role"] == "assistant"
        assert messages[-1]["content"] == reconstructed
        assert messages[-1]["feedback_score"] >= 1
    finally:
        settings.llm_provider = original_provider


def test_interview_stream_tracks_round_state_and_finishes_with_summary_status() -> None:
    original_provider = settings.llm_provider
    settings.llm_provider = "mock"
    headers, job_id, _resume_id = _prepare_user_and_job()

    try:
        start_resp = client.post(
            "/api/v1/interview/session/start",
            headers=headers,
            json={"job_id": job_id, "mode": "standard"},
        )
        assert start_resp.status_code == 201
        start_data = start_resp.json()["data"]
        session_id = start_data["session_id"]
        assert start_data["status"] == "waiting_user"
        assert start_data["round_index"] == 1
        assert start_data["messages"][0]["round_index"] == 1
        assert start_data["messages"][0]["question_id"] == "q-1"

        answers = [
            "第一轮我会先澄清目标，再拆分任务并给出可验证结果。",
            "第二轮我会用具体项目说明我如何定位问题、写测试并复盘。",
            "第三轮我会总结风险、指标和下一步改进，确保结果可落地。",
        ]
        for index, answer in enumerate(answers, start=1):
            with client.stream(
                "POST",
                f"/api/v1/interview/session/{session_id}/answer/stream",
                headers=headers,
                json={"answer": answer},
            ) as response:
                assert response.status_code == 200
                body = "".join(response.iter_text())
            events = _parse_sse_events(body)
            assert events[0]["metadata"]["round_index"] == index
            assert events[0]["metadata"]["question_id"] == f"q-{index}"
            assert events[-1]["metadata"]["round_index"] == index
            assert events[-1]["metadata"]["question_id"] == f"q-{index}"

        detail_resp = client.get(f"/api/v1/interview/session/{session_id}", headers=headers)
        detail_data = detail_resp.json()["data"]
        assert detail_data["status"] == "summary"
        assert detail_data["round_index"] == 3
        assert detail_data["max_rounds"] == 3
        assert detail_data["messages"][-1]["session_status"] == "summary"
        assert detail_data["messages"][-1]["round_index"] == 3
        assert detail_data["messages"][-1]["question_id"] == "q-3"
        assert detail_data["report"]["status"] == "summary_ready"
        assert detail_data["report"]["agent_summary"]["evidence_chain"]
        assert detail_data["report"]["agent_summary"]["score_dimensions"]

        with session_local() as session:
            user_id = session.execute(text("SELECT user_id FROM interview_sessions WHERE id = :session_id"), {"session_id": session_id}).scalar_one()
            interview_memory_count = session.execute(
                text("SELECT count(*) FROM assistant_memories WHERE user_id = :user_id AND assistant_type = 'interview_assistant' AND deleted_at IS NULL"),
                {"user_id": str(user_id)},
            ).scalar_one()
            ai_count = session.execute(
                text("SELECT count(*) FROM assistant_memories WHERE user_id = :user_id AND assistant_type = 'ai_assistant'"),
                {"user_id": str(user_id)},
            ).scalar_one()
        assert interview_memory_count == 0
        assert ai_count == 0
    finally:
        settings.llm_provider = original_provider


def test_interview_stream_metadata_uses_interview_assistant_memory_namespace() -> None:
    original_provider = settings.llm_provider
    settings.llm_provider = "mock"
    headers, job_id, _resume_id = _prepare_user_and_job()

    try:
        start_resp = client.post(
            "/api/v1/interview/session/start",
            headers=headers,
            json={"job_id": job_id, "mode": "standard"},
        )
        session_id = start_resp.json()["data"]["session_id"]

        with client.stream(
            "POST",
            f"/api/v1/interview/session/{session_id}/answer/stream",
            headers=headers,
            json={"answer": "我会用 STAR 结构说明项目背景、个人动作和结果。"},
        ) as response:
            assert response.status_code == 200
            body = "".join(response.iter_text())

        events = _parse_sse_events(body)
        metadata = events[-1]["metadata"]

        assert metadata["assistant_type"] == "interview_assistant"
        assert metadata["agent_name"] == "interview_feedback"
        assert metadata["memory_scope"]["short_term"] == "interview_sessions.report.agent_state"
        assert metadata["memory_scope"]["long_term"] is None
        assert metadata["memory_scope"]["compression"] == "agent_state.session_summary"
        assert metadata["memory_updates"]["assistant_type"] == "interview_assistant"
        assert metadata["memory_updates"]["storage"] == "interview_sessions.report.agent_state"
        assert metadata["memory_snapshot"]["available"] is False
        assert metadata["memory_snapshot"]["assistant_type"] == "interview_assistant"
        assert metadata["memory_snapshot"]["path"] is None
        assert "ai_assistant" not in json.dumps(metadata["memory_used"], ensure_ascii=False)
    finally:
        settings.llm_provider = original_provider


def test_interview_start_requires_a_default_parsed_resume() -> None:
    original_provider = settings.llm_provider
    settings.llm_provider = "mock"
    headers, job_id, _resume_id = _prepare_user_and_job(with_resume=False)

    try:
        start_resp = client.post(
            "/api/v1/interview/session/start",
            headers=headers,
            json={"job_id": job_id, "mode": "standard"},
        )
        assert start_resp.status_code == 400
        assert start_resp.json()["code"] == 5004
    finally:
        settings.llm_provider = original_provider


def test_interview_sessions_can_be_listed_with_resume_context() -> None:
    original_provider = settings.llm_provider
    settings.llm_provider = "mock"
    headers, job_id, resume_id = _prepare_user_and_job()

    try:
        start_resp = client.post(
            "/api/v1/interview/session/start",
            headers=headers,
            json={"job_id": job_id, "mode": "standard"},
        )
        session_id = start_resp.json()["data"]["session_id"]

        list_resp = client.get("/api/v1/interview/sessions", headers=headers)
        assert list_resp.status_code == 200
        list_body = list_resp.json()
        assert list_body["code"] == 0
        assert list_body["data"]["total"] == 1
        item = list_body["data"]["sessions"][0]
        assert item["session_id"] == session_id
        assert item["job_title"] == "AI Backend Intern"
        assert item["resume_id"] == resume_id
        assert item["resume_file_name"] == "interview-resume.docx"
        assert item["status"] == "waiting_user"
    finally:
        settings.llm_provider = original_provider


def test_interview_start_reuses_same_job_session_by_default_and_can_force_new() -> None:
    original_provider = settings.llm_provider
    settings.llm_provider = "mock"
    headers, job_id, resume_id = _prepare_user_and_job()

    try:
        first_resp = client.post(
            "/api/v1/interview/session/start",
            headers=headers,
            json={"job_id": job_id, "mode": "standard"},
        )
        second_resp = client.post(
            "/api/v1/interview/session/start",
            headers=headers,
            json={"job_id": job_id, "mode": "standard"},
        )
        third_resp = client.post(
            "/api/v1/interview/session/start",
            headers=headers,
            json={"job_id": job_id, "mode": "standard", "resume_id": resume_id, "force_new": True},
        )

        first_session_id = first_resp.json()["data"]["session_id"]
        assert second_resp.status_code == 201
        assert second_resp.json()["data"]["session_id"] == first_session_id
        assert second_resp.json()["data"]["reused"] is True
        assert third_resp.status_code == 201
        assert third_resp.json()["data"]["session_id"] != first_session_id
        assert third_resp.json()["data"]["reused"] is False
    finally:
        settings.llm_provider = original_provider


def test_interview_opening_question_changes_with_job_function() -> None:
    original_provider = settings.llm_provider
    settings.llm_provider = "mock"
    headers, job_id, _resume_id = _prepare_user_and_job(
        title="数据分析实习生",
        jd_text="负责 SQL 指标体系、业务分析、A/B 测试和可视化看板。",
    )

    try:
        start_resp = client.post(
            "/api/v1/interview/session/start",
            headers=headers,
            json={"job_id": job_id, "mode": "standard"},
        )
        content = start_resp.json()["data"]["messages"][0]["content"]
        assert "数据分析实习生" in content
        assert "SQL 指标体系" in content
        assert "指标" in content
        assert "A/B" in content
    finally:
        settings.llm_provider = original_provider


def test_interview_session_report_requires_existing_answers() -> None:
    original_provider = settings.llm_provider
    settings.llm_provider = "mock"
    headers, job_id, _resume_id = _prepare_user_and_job()
    try:
        start_resp = client.post(
            "/api/v1/interview/session/start",
            headers=headers,
            json={"job_id": job_id, "mode": "pressure"},
        )
        session_id = start_resp.json()["data"]["session_id"]

        report_resp = client.get(f"/api/v1/interview/session/{session_id}/report", headers=headers)
        assert report_resp.status_code == 400
        assert report_resp.json()["code"] == 5002
    finally:
        settings.llm_provider = original_provider
