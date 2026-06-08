from __future__ import annotations

import io
import zipfile

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import session_local
from app.main import app
from app.tasks.resume_tasks import process_pending_resumes_once

client = TestClient(app)


class _SequencedResumeProvider:
    name = "claude"
    model = "gemma4:26b"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def generate(self, prompt: str, **kwargs) -> str:
        self.calls.append(prompt)
        if len(self.calls) == 1:
            return (
                '{'
                '"summary":"FastAPI backend intern candidate with SQL projects",'
                '"education":[{"school":"Demo University","degree":"Bachelor"}],'
                '"experience":[{"company":"InternAgent","role":"Backend Intern"}],'
                '"projects":[{"name":"InternAgent","description":"FastAPI Qdrant agent project"}],'
                '"skills":["Python","FastAPI","SQL","Qdrant"]'
                '}'
            )
        return (
            '{'
            '"overall_score":91,'
            '"label":"strong",'
            '"summary":"The resume has a clear backend direction and relevant project evidence.",'
            '"dimensions":['
            '{"dimension":"教育背景","score":80,"weight":0.1,"evidence":["Demo University Bachelor"],"problems":["缺少 GPA 或相关课程"],"suggestions":["补充相关课程或 GPA"],"confidence":0.83},'
            '{"dimension":"技能匹配","score":92,"weight":0.2,"evidence":["Python、FastAPI、SQL、Qdrant 与后端岗位相关"],"problems":[],"suggestions":["按岗位补充 Redis 或 Docker"],"confidence":0.9},'
            '{"dimension":"项目经历","score":93,"weight":0.25,"evidence":["InternAgent 项目包含 FastAPI Qdrant agent project"],"problems":["结果指标还不够量化"],"suggestions":["补充接口响应时间、检索命中率、测试覆盖率"],"confidence":0.91},'
            '{"dimension":"实习/实践","score":88,"weight":0.15,"evidence":["包含 Backend Intern 经历"],"problems":["缺少协作对象"],"suggestions":["补充和产品、前端或模型服务协作方式"],"confidence":0.86},'
            '{"dimension":"表达质量","score":90,"weight":0.15,"evidence":["后端方向明确"],"problems":["贡献边界还可以更具体"],"suggestions":["用 STAR 法写本人负责模块"],"confidence":0.87},'
            '{"dimension":"量化结果","score":70,"weight":0.1,"evidence":["项目描述有技术栈但数字较少"],"problems":["缺少性能或业务指标"],"suggestions":["补充请求耗时、并发量或命中率"],"confidence":0.82},'
            '{"dimension":"风险项","score":90,"weight":0.05,"evidence":["未发现明显夸大"],"problems":[],"suggestions":["保持可验证表达"],"confidence":0.85}'
            '],'
            '"highlights":["Clear backend stack","Relevant agent project","Search and database keywords"],'
            '"risks":["Add quantified impact"],'
            '"next_actions":["Add metrics to the project section","Tailor keywords for backend internship"]'
            '}'
        )


class _InvalidResumeProvider:
    name = "claude"
    model = "gemma4:26b"

    async def generate(self, prompt: str, **kwargs) -> str:
        return ""


def _docx_bytes(text: str) -> bytes:
    document_xml = f"""<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>
<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">
  <w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body>
</w:document>"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "")
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def _reset_data() -> None:
    with session_local() as session:
        session.execute(text("DELETE FROM chat_sessions"))
        session.execute(text("DELETE FROM interview_sessions"))
        session.execute(text("DELETE FROM applications"))
        session.execute(text("DELETE FROM resumes"))
        session.execute(text("DELETE FROM jobs"))
        session.execute(text("DELETE FROM users"))
        session.commit()


def _auth_headers() -> dict[str, str]:
    _reset_data()
    register_resp = client.post(
        "/api/v1/auth/register",
        json={"email": "real-resume@example.com", "password": "Test1234!", "name": "Resume User"},
    )
    token = register_resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_docx_worker_extracts_text_parses_with_model_and_persists_score(monkeypatch) -> None:
    provider = _SequencedResumeProvider()
    monkeypatch.setattr("app.services.resume_service.get_provider", lambda: provider)
    headers = _auth_headers()

    upload_resp = client.post(
        "/api/v1/resume/upload",
        headers=headers,
        files={
            "file": (
                "backend_resume.docx",
                _docx_bytes("Python FastAPI SQL Qdrant InternAgent backend project"),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert upload_resp.status_code == 200
    resume_id = upload_resp.json()["data"]["resume_id"]

    processing_resp = client.get(f"/api/v1/resume/{resume_id}/status", headers=headers)
    assert processing_resp.json()["data"]["parse_status"] == "processing"
    assert processing_resp.json()["data"]["score"] is None

    processed = process_pending_resumes_once()
    assert processed == 1

    done_resp = client.get(f"/api/v1/resume/{resume_id}/status", headers=headers)
    body = done_resp.json()["data"]
    assert body["parse_status"] == "done"
    assert body["parsed_content"]["skills"] == ["Python", "FastAPI", "SQL", "Qdrant"]
    assert body["score"]["overall_score"] == 91
    assert body["score"]["source"] == "gemma4"
    assert body["score"]["model"] == "gemma4:26b"
    assert body["score"]["status"] == "ready"
    assert body["score"]["rubric_version"] == "resume_score_v1"
    assert body["score"]["llm_review"]["status"] == "ready"
    assert any(item["dimension"] == "项目经历" and item["evidence"] for item in body["score"]["dimensions"])

    with session_local() as session:
        row = session.execute(
            text("SELECT score_report, is_default FROM resumes WHERE id = :resume_id"),
            {"resume_id": resume_id},
        ).mappings().one()
    assert row["score_report"]["overall_score"] == 91
    assert row["score_report"]["rubric_version"] == "resume_score_v1"
    assert row["is_default"] is True


def test_worker_falls_back_to_rule_parse_and_score_when_model_returns_empty(monkeypatch) -> None:
    monkeypatch.setattr("app.services.resume_service.get_provider", lambda: _InvalidResumeProvider())
    headers = _auth_headers()
    upload_resp = client.post(
        "/api/v1/resume/upload",
        headers=headers,
        files={"file": ("fallback_resume.pdf", b"Python SQL FastAPI project with Redis metrics", "application/pdf")},
    )
    resume_id = upload_resp.json()["data"]["resume_id"]

    assert process_pending_resumes_once() == 1

    done_resp = client.get(f"/api/v1/resume/{resume_id}/status", headers=headers)
    body = done_resp.json()["data"]
    assert body["parse_status"] == "done"
    assert "Python" in body["parsed_content"]["skills"]
    assert body["score"]["source"] == "fallback_rule"
    assert body["score"]["status"] == "fallback"
    assert body["score"]["rubric_version"] == "resume_score_v1"
    assert body["score"]["rule_score"]["checks"]["has_project_name"] is True
