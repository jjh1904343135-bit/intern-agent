from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import session_local
from app.main import app
from app.models.application import Application
from app.models.job import Job
from app.tasks.application_tasks import advance_pending_applications_once

client = TestClient(app)


def _reset_application_data() -> None:
    with session_local() as session:
        session.execute(text("DELETE FROM chat_sessions"))
        session.execute(text("DELETE FROM interview_sessions"))
        session.execute(text("DELETE FROM applications"))
        session.execute(text("DELETE FROM resumes"))
        session.execute(text("DELETE FROM jobs"))
        session.execute(text("DELETE FROM users"))
        session.commit()


def _prepare_auth_headers() -> tuple[dict[str, str], str]:
    _reset_application_data()
    register_resp = client.post(
        "/api/v1/auth/register",
        json={"email": "apply@example.com", "password": "Test1234!", "name": "Apply User"},
    )
    body = register_resp.json()["data"]
    headers = {"Authorization": f"Bearer {body['access_token']}"}

    upload_resp = client.post(
        "/api/v1/resume/upload",
        headers=headers,
        files={"file": ("apply_resume.pdf", b"Python SQL FastAPI", "application/pdf")},
    )
    resume_id = upload_resp.json()["data"]["resume_id"]

    with session_local() as session:
        session.execute(
            text(
                "UPDATE resumes SET parse_status='done', parsed_content=cast(:content as jsonb), is_default=true WHERE id=:resume_id"
            ),
            {
                "resume_id": resume_id,
                "content": '{"skills": ["Python", "SQL"], "projects": [{"name": "InternAgent"}]}',
            },
        )
        session.add(
            Job(
                external_id="job-day6-001",
                source="greenhouse",
                title="Backend Intern",
                company="InternAgent",
                city="Shanghai",
                salary_range="200/day",
                duration="3 months",
                jd_text="Python SQL FastAPI",
                apply_url="https://boards.greenhouse.io/internagent/jobs/1",
                is_active=True,
            )
        )
        session.commit()
        job = session.query(Job).filter(Job.external_id == "job-day6-001").one()
        return headers, str(job.id)


def test_save_application_and_list_flow() -> None:
    headers, job_id = _prepare_auth_headers()

    apply_resp = client.post(f"/api/v1/jobs/{job_id}/apply", headers=headers, json={})
    assert apply_resp.status_code == 201
    apply_body = apply_resp.json()
    assert apply_body["code"] == 0
    assert apply_body["data"]["status"] == "saved"
    assert apply_body["data"]["timeline"] == ["saved"]
    assert apply_body["data"]["job_id"] == job_id

    list_resp = client.get("/api/v1/applications", headers=headers)
    assert list_resp.status_code == 200
    list_body = list_resp.json()
    assert list_body["code"] == 0
    assert list_body["data"]["total"] == 1
    assert list_body["data"]["items"][0]["status"] == "saved"


def test_application_manual_status_flow_is_user_controlled() -> None:
    headers, job_id = _prepare_auth_headers()
    apply_resp = client.post(f"/api/v1/jobs/{job_id}/apply", headers=headers, json={})
    application_id = apply_resp.json()["data"]["application_id"]

    advanced = advance_pending_applications_once()
    assert advanced == 0

    opened_resp = client.post(f"/api/v1/applications/{application_id}/mark-opened", headers=headers)
    assert opened_resp.status_code == 200
    assert opened_resp.json()["data"]["status"] == "opened"
    assert opened_resp.json()["data"]["timeline"] == ["saved", "opened"]

    applied_resp = client.post(f"/api/v1/applications/{application_id}/mark-applied", headers=headers)
    assert applied_resp.status_code == 200
    assert applied_resp.json()["data"]["status"] == "applied_manual"
    assert applied_resp.json()["data"]["timeline"] == ["saved", "opened", "applied_manual"]

    with session_local() as session:
        application = session.query(Application).filter(Application.id == application_id).one()
        assert application.status == "applied_manual"


def test_application_followup_statuses_and_manual_notes_are_persisted() -> None:
    headers, job_id = _prepare_auth_headers()
    apply_resp = client.post(f"/api/v1/jobs/{job_id}/apply", headers=headers, json={})
    application_id = apply_resp.json()["data"]["application_id"]

    client.post(f"/api/v1/applications/{application_id}/mark-opened", headers=headers)
    client.post(f"/api/v1/applications/{application_id}/mark-applied", headers=headers)

    waiting_resp = client.post(f"/api/v1/applications/{application_id}/mark-waiting-feedback", headers=headers)
    assert waiting_resp.status_code == 200
    assert waiting_resp.json()["data"]["status"] == "waiting_feedback"

    interview_resp = client.post(f"/api/v1/applications/{application_id}/mark-interviewing", headers=headers)
    assert interview_resp.status_code == 200
    assert interview_resp.json()["data"]["status"] == "interviewing"

    notes_resp = client.patch(
        f"/api/v1/applications/{application_id}/notes",
        headers=headers,
        json={
            "platform": "company_site",
            "applied_date": "2026-05-06",
            "hr_contact": "hr@example.com",
            "feedback_result": "waiting for screen",
        },
    )
    assert notes_resp.status_code == 200
    assert notes_resp.json()["data"]["tracking_notes"]["platform"] == "company_site"
    assert notes_resp.json()["data"]["tracking_notes"]["hr_contact"] == "hr@example.com"

    closed_resp = client.post(f"/api/v1/applications/{application_id}/mark-closed", headers=headers)
    assert closed_resp.status_code == 200
    assert closed_resp.json()["data"]["status"] == "closed"
    assert closed_resp.json()["data"]["status_flow"] == [
        "saved",
        "opened",
        "applied_manual",
        "waiting_feedback",
        "interviewing",
        "closed",
    ]
