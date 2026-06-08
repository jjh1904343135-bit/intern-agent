from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import session_local
from app.main import app
from app.tasks.resume_tasks import process_pending_resumes_once

client = TestClient(app)


class _FakeResumeReviewer:
    name = "claude"
    model = "gemma4:26b"

    async def generate(self, prompt: str, **kwargs) -> str:
        if "Extract JSON" in prompt:
            return (
                '{'
                '"summary":"Backend resume with Python and SQL",'
                '"education":[],'
                '"experience":[],'
                '"projects":[{"name":"InternAgent Demo Project"}],'
                '"skills":["Python","SQL"]'
                '}'
            )
        return (
            '{'
            '"overall_score":88,'
            '"label":"strong",'
            '"summary":"Project experience and skills are clear.",'
            '"dimensions":['
            '{"dimension":"教育背景","score":70,"weight":0.1,"evidence":["简历暂未提取到教育经历"],"problems":["教育背景不够完整"],"suggestions":["补充学校、专业和毕业时间"],"confidence":0.72},'
            '{"dimension":"技能匹配","score":86,"weight":0.2,"evidence":["包含 Python 和 SQL"],"problems":["缺少目标岗位关键词"],"suggestions":["补充 FastAPI、Redis 或 Docker 等岗位关键词"],"confidence":0.86},'
            '{"dimension":"项目经历","score":88,"weight":0.25,"evidence":["包含 InternAgent Demo Project 项目"],"problems":["缺少量化指标"],"suggestions":["补充接口响应时间、检索命中率或测试覆盖率"],"confidence":0.88},'
            '{"dimension":"实习/实践","score":65,"weight":0.15,"evidence":["简历结构中暂未提取到实习经历"],"problems":["实践经历较弱"],"suggestions":["补充协作、交付和上线流程"],"confidence":0.7},'
            '{"dimension":"表达质量","score":82,"weight":0.15,"evidence":["项目和技能表达较清晰"],"problems":["职责边界还不够明确"],"suggestions":["说明本人负责模块边界"],"confidence":0.82},'
            '{"dimension":"量化结果","score":58,"weight":0.1,"evidence":["当前项目描述缺少数字结果"],"problems":["没有量化成效"],"suggestions":["补充性能、规模或转化指标"],"confidence":0.78},'
            '{"dimension":"风险项","score":90,"weight":0.05,"evidence":["没有明显夸大表述"],"problems":[],"suggestions":["继续保持真实表达"],"confidence":0.84}'
            '],'
            '"highlights":["Focused skills","Clear project","ATS readable"],'
            '"risks":["Add quantified results"],'
            '"next_actions":["Add metrics","Tailor summary","Trim repeated skills"]'
            '}'
        )


class _EmptyResumeReviewer:
    name = "claude"
    model = "gemma4:26b"

    async def generate(self, prompt: str, **kwargs) -> str:
        return ""


def _reset_auth_and_resume_data() -> None:
    with session_local() as session:
        session.execute(text("DELETE FROM chat_sessions"))
        session.execute(text("DELETE FROM interview_sessions"))
        session.execute(text("DELETE FROM applications"))
        session.execute(text("DELETE FROM resumes"))
        session.execute(text("DELETE FROM jobs"))
        session.execute(text("DELETE FROM users"))
        session.commit()


def _auth_headers() -> dict[str, str]:
    _reset_auth_and_resume_data()
    register_resp = client.post(
        "/api/v1/auth/register",
        json={"email": "resume@example.com", "password": "Test1234!", "name": "Resume User"},
    )
    token = register_resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_resume_upload_and_status_flow(monkeypatch) -> None:
    monkeypatch.setattr("app.services.resume_service.get_provider", lambda: _FakeResumeReviewer())
    headers = _auth_headers()
    upload_resp = client.post(
        "/api/v1/resume/upload",
        headers=headers,
        files={"file": ("sample_resume.pdf", b"Python SQL FastAPI resume content", "application/pdf")},
    )

    assert upload_resp.status_code == 200
    upload_body = upload_resp.json()
    assert upload_body["code"] == 0
    assert upload_body["data"]["parse_status"] == "processing"
    assert upload_body["data"]["estimated_seconds"] == 8
    assert upload_body["data"]["progress"]["current_stage"] == "uploaded"
    assert [stage["key"] for stage in upload_body["data"]["progress"]["stages"]] == [
        "uploaded",
        "extracting_text",
        "structuring",
        "scoring",
        "completed",
    ]

    resume_id = upload_body["data"]["resume_id"]
    status_resp = client.get(f"/api/v1/resume/{resume_id}/status", headers=headers)
    assert status_resp.status_code == 200
    processing_data = status_resp.json()["data"]
    assert processing_data["parse_status"] == "processing"
    assert processing_data["progress"]["current_stage"] == "extracting_text"
    assert processing_data["progress"]["percent"] >= 20

    processed = process_pending_resumes_once()
    assert processed >= 1

    done_resp = client.get(f"/api/v1/resume/{resume_id}/status", headers=headers)
    assert done_resp.status_code == 200
    done_body = done_resp.json()
    assert done_body["data"]["parse_status"] == "done"
    assert done_body["data"]["progress"]["current_stage"] == "completed"
    assert done_body["data"]["progress"]["percent"] == 100
    assert done_body["data"]["parsed_content"]["skills"] == ["Python", "SQL"]
    assert done_body["data"]["score"]["overall_score"] == 88
    assert done_body["data"]["score"]["source"] == "gemma4"
    assert done_body["data"]["score"]["status"] == "ready"
    assert done_body["data"]["score"]["summary"]
    assert done_body["data"]["score"]["next_actions"]
    score = done_body["data"]["score"]
    assert score["rubric_version"] == "resume_score_v1"
    assert score["rule_score"]["version"] == "resume_rule_v1"
    assert score["llm_review"]["status"] == "ready"
    assert len(score["dimensions"]) == 7
    project_dimension = next(item for item in score["dimensions"] if item["dimension"] == "项目经历")
    assert project_dimension["weight"] == 0.25
    assert "包含 InternAgent Demo Project 项目" in project_dimension["evidence"]
    assert "缺少量化指标" in project_dimension["problems"]
    assert "补充接口响应时间、检索命中率或测试覆盖率" in project_dimension["suggestions"]
    assert 0 <= project_dimension["confidence"] <= 1


def test_resume_upload_rejects_invalid_extension() -> None:
    headers = _auth_headers()
    upload_resp = client.post(
        "/api/v1/resume/upload",
        headers=headers,
        files={"file": ("notes.txt", b"not allowed", "text/plain")},
    )

    assert upload_resp.status_code == 400
    body = upload_resp.json()
    assert body["code"] == 2001


def test_resume_status_falls_back_when_llm_returns_empty_content(monkeypatch) -> None:
    monkeypatch.setattr("app.services.resume_service.get_provider", lambda: _EmptyResumeReviewer())
    headers = _auth_headers()
    upload_resp = client.post(
        "/api/v1/resume/upload",
        headers=headers,
        files={"file": ("sample_resume.pdf", b"Python SQL resume content", "application/pdf")},
    )
    resume_id = upload_resp.json()["data"]["resume_id"]

    processed = process_pending_resumes_once()
    assert processed >= 1

    done_resp = client.get(f"/api/v1/resume/{resume_id}/status", headers=headers)
    assert done_resp.status_code == 200
    done_body = done_resp.json()
    assert done_body["data"]["score"]["source"] == "fallback_rule"
    assert done_body["data"]["score"]["status"] == "fallback"
    assert done_body["data"]["score"]["rubric_version"] == "resume_score_v1"
    assert len(done_body["data"]["score"]["dimensions"]) == 7
    assert done_body["data"]["score"]["rule_score"]["checks"]["has_skill_keywords"] is True
    assert done_body["data"]["score"]["llm_review"]["status"] == "fallback"


def test_resume_status_exposes_specific_failure_reason() -> None:
    headers = _auth_headers()
    upload_resp = client.post(
        "/api/v1/resume/upload",
        headers=headers,
        files={"file": ("empty_resume.pdf", b"tiny", "application/pdf")},
    )
    resume_id = upload_resp.json()["data"]["resume_id"]

    with session_local() as session:
        session.execute(
            text("UPDATE resumes SET parse_status='failed', parse_error='extracted text is too short' WHERE id = :resume_id"),
            {"resume_id": resume_id},
        )
        session.commit()

    status_resp = client.get(f"/api/v1/resume/{resume_id}/status", headers=headers)

    assert status_resp.status_code == 200
    data = status_resp.json()["data"]
    assert data["parse_status"] == "failed"
    assert data["progress"]["current_stage"] == "failed"
    assert data["progress"]["failure_reason"]["code"] == "text_too_short"
    assert "文本太少" in data["progress"]["failure_reason"]["message"]
