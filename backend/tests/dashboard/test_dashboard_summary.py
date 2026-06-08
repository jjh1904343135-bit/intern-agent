from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import session_local
from app.main import app
from app.models.application import Application
from app.models.chat_session import ChatSession
from app.models.interview_session import InterviewSession
from app.models.job import Job
from app.models.resume import Resume

client = TestClient(app)


def _reset_dashboard_data() -> None:
    with session_local() as session:
        session.execute(text("DELETE FROM chat_sessions"))
        session.execute(text("DELETE FROM interview_sessions"))
        session.execute(text("DELETE FROM applications"))
        session.execute(text("DELETE FROM resumes"))
        session.execute(text("DELETE FROM jobs"))
        session.execute(text("DELETE FROM users"))
        session.commit()


def _prepare_dashboard_fixture() -> dict[str, str]:
    _reset_dashboard_data()
    register_resp = client.post(
        "/api/v1/auth/register",
        json={"email": "dashboard@example.com", "password": "Test1234!", "name": "仪表盘用户"},
    )
    payload = register_resp.json()["data"]
    user_id = payload["user_id"]

    with session_local() as session:
        resume = Resume(
            user_id=user_id,
            file_url="/tmp/dashboard_resume.pdf",
            file_name="dashboard_resume.pdf",
            parse_status="done",
            parsed_content={"skills": ["Python", "SQL"], "projects": [{"name": "InternAgent"}]},
            score_report={
                "overall_score": 84,
                "label": "良好",
                "summary": "已经具备较强的工程基础，但可以继续加强项目结果表达。",
                "dimensions": {
                    "completeness": 82,
                    "skills_depth": 86,
                    "project_quality": 83,
                    "ats_readiness": 85,
                },
                "highlights": ["技能栈清晰"],
                "risks": ["缺少量化结果"],
                "next_actions": ["补一段岗位导向摘要", "把项目成果写成数字结果"],
                "source": "gemma4",
                "model": "gemma4:26b",
            },
            is_default=True,
        )
        job = Job(
            external_id="dashboard-job-001",
            source="manual",
            title="Backend Intern",
            company="InternAgent",
            city="Shanghai",
            salary_range="250/day",
            duration="3 months",
            jd_text="Python FastAPI SQL",
            apply_url="https://example.com/dashboard-job",
            is_active=True,
        )
        session.add_all([resume, job])
        session.commit()
        session.refresh(resume)
        session.refresh(job)

        application = Application(
            user_id=user_id,
            job_id=str(job.id),
            resume_id=str(resume.id),
            status="submitted",
            source="manual",
        )
        interview = InterviewSession(
            user_id=user_id,
            job_id=str(job.id),
            mode="standard",
            messages=[{"role": "assistant", "content": "请介绍一下你自己"}],
            report={"overall_score": 78},
        )
        chat = ChatSession(
            user_id=user_id,
            messages=[
                {"role": "user", "content": "怎么优化项目描述？"},
                {"role": "assistant", "content": "先把结果量化，再写职责和技术栈。"},
            ],
            agent_states={"supervisor": "done"},
            last_agent="supervisor",
            token_count=42,
        )
        session.add_all([application, interview, chat])
        session.commit()

    return {
        "Authorization": f"Bearer {payload['access_token']}",
    }


def test_dashboard_summary_returns_aggregated_cards() -> None:
    headers = _prepare_dashboard_fixture()

    response = client.get("/api/v1/dashboard/summary", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["overview"]["resume_count"] == 1
    assert body["data"]["overview"]["applications_total"] == 1
    assert body["data"]["resume"]["score"]["overall_score"] == 84
    assert body["data"]["applications"]["status_breakdown"]["submitted"] == 1
    assert body["data"]["interview"]["latest"]["overall_score"] == 78
    assert "量化" in body["data"]["chat"]["latest_preview"]["preview"]
    assert len(body["data"]["next_actions"]) >= 1
    recommended = body["data"]["recommended_actions"]
    assert len(recommended) >= 1
    assert {"kind", "title", "description", "href", "priority"} <= set(recommended[0].keys())
    assert any(action["kind"] == "application_followup" for action in recommended)
