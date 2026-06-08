from __future__ import annotations

import re
from typing import Any

from app.agents.interview.models import CandidateProfile, JobProfile
from app.tools.job_discovery import extract_skills, infer_job_type


EXTRA_SKILLS = {
    "RAG": ["rag", "检索增强", "召回", "向量检索"],
    "Qdrant": ["qdrant"],
    "LLM": ["llm", "大模型", "gemma", "claude", "gpt"],
    "Agent": ["agent", "智能体", "多 agent", "multi-agent"],
    "Docker": ["docker", "compose", "容器"],
    "pytest": ["pytest", "tdd", "测试"],
    "SSE": ["sse", "stream", "流式"],
}


def get_job_detail(*, job=None, url: str | None = None, raw_jd: str | None = None) -> dict[str, Any]:
    """Normalize job inputs now; later this boundary can call MCP/web/url tools."""
    if job is not None:
        return {
            "title": job.title,
            "company": job.company,
            "city": job.city,
            "salary": job.salary_range,
            "jd_text": job.jd_text or "",
            "apply_url": job.apply_url,
            "metadata": job.jd_parsed or {},
        }
    if raw_jd:
        return {"title": "自定义 JD", "company": None, "city": None, "salary": None, "jd_text": raw_jd, "apply_url": url}
    return {"title": "未知岗位", "company": None, "city": None, "salary": None, "jd_text": "", "apply_url": url}


def extract_job_profile(raw_job: dict[str, Any]) -> JobProfile:
    title = str(raw_job.get("title") or "未知岗位")
    jd_text = str(raw_job.get("jd_text") or "")
    text = f"{title} {jd_text}"
    skills = _extract_all_skills(text)
    tags = _domain_tags(text=text, skills=skills)
    return JobProfile(
        title=title,
        company=raw_job.get("company"),
        level=_infer_level(title=title, jd_text=jd_text),
        domain_tags=tags,
        must_have_skills=skills,
        nice_to_have_skills=_nice_to_have_skills(jd_text=jd_text, skills=skills),
        responsibilities=_responsibilities(jd_text),
        interview_focus=_interview_focus(text=text, skills=skills),
        language=_language(text),
    )


def extract_candidate_profile(*, resume_id: str, file_name: str | None, parsed_resume: dict[str, Any], job_profile: JobProfile) -> CandidateProfile:
    skills = _extract_all_skills(" ".join([*(parsed_resume.get("skills") or []), str(parsed_resume.get("summary") or ""), _projects_text(parsed_resume)]))
    matched = _skill_intersection(skills, job_profile.must_have_skills)
    missing = [skill for skill in job_profile.must_have_skills if skill not in matched]
    return CandidateProfile(
        resume_id=resume_id,
        file_name=file_name,
        summary=str(parsed_resume.get("summary") or ""),
        skills=skills,
        projects=[item for item in list(parsed_resume.get("projects") or []) if isinstance(item, dict)],
        experience=[item for item in list(parsed_resume.get("experience") or []) if isinstance(item, dict)],
        education=[item for item in list(parsed_resume.get("education") or []) if isinstance(item, dict)],
        matched_skills=matched,
        missing_skills=missing,
    )


def _extract_all_skills(text: str) -> list[str]:
    skills = extract_skills(text)
    normalized = text.lower()
    for skill, patterns in EXTRA_SKILLS.items():
        if any(pattern.lower() in normalized for pattern in patterns):
            skills.append(skill)
    return _unique(skills)


def _skill_intersection(left: list[str], right: list[str]) -> list[str]:
    right_map = {item.lower(): item for item in right}
    matched: list[str] = []
    for skill in left:
        if skill.lower() in right_map:
            matched.append(right_map[skill.lower()])
    return _unique(matched)


def _infer_level(*, title: str, jd_text: str) -> str:
    text = f"{title} {jd_text}".lower()
    job_type = infer_job_type(title, jd_text)
    if job_type == "intern":
        return "intern"
    if any(token in text for token in ["manager", "负责人", "经理"]):
        return "manager"
    if any(token in text for token in ["staff", "principal", "专家"]):
        return "staff"
    if any(token in text for token in ["senior", "资深", "3-5", "5 年"]):
        return "senior"
    if any(token in text for token in ["junior", "初级", "应届", "校招"]):
        return "junior"
    return "mid"


def _domain_tags(*, text: str, skills: list[str]) -> list[str]:
    tags: list[str] = []
    normalized = text.lower()
    if {"LLM", "RAG", "Agent"} & set(skills) or "大模型" in normalized:
        tags.extend(["LLM", "RAG", "Agent"])
    if {"Python", "FastAPI", "Redis", "SQL"} & set(skills) or "后端" in text:
        tags.append("Backend")
    if "推荐" in text or "recsys" in normalized:
        tags.append("Recsys")
    if "产品" in text or "product" in normalized:
        tags.append("Product")
    return _unique(tags or skills[:3])


def _nice_to_have_skills(*, jd_text: str, skills: list[str]) -> list[str]:
    if any(term in jd_text for term in ["加分", "优先", "nice to have", "plus"]):
        return skills[-3:]
    return []


def _responsibilities(jd_text: str) -> list[str]:
    parts = [item.strip(" -•\t") for item in re.split(r"[。；;\n]", jd_text) if item.strip()]
    return parts[:6] or ["围绕岗位核心职责完成项目交付和协作沟通"]


def _interview_focus(*, text: str, skills: list[str]) -> list[str]:
    focus: list[str] = ["项目经历"]
    if {"LLM", "RAG", "Agent", "Qdrant"} & set(skills):
        focus.extend(["RAG/Agent 设计", "工程化与评测"])
    if {"Python", "FastAPI", "Redis", "SQL"} & set(skills):
        focus.extend(["接口设计", "后端工程", "系统设计"])
    if "产品" in text:
        focus.extend(["需求拆解", "跨团队协作"])
    focus.append("行为面")
    return _unique(focus)


def _language(text: str) -> str:
    has_zh = any("\u4e00" <= char <= "\u9fff" for char in text)
    has_en = any("a" <= char.lower() <= "z" for char in text)
    if has_zh and has_en:
        return "mixed"
    return "zh" if has_zh else "en"


def _projects_text(parsed_resume: dict[str, Any]) -> str:
    chunks: list[str] = []
    for project in parsed_resume.get("projects") or []:
        if isinstance(project, dict):
            chunks.extend(str(project.get(key) or "") for key in ("name", "description", "impact"))
    return " ".join(chunks)


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = str(value).strip()
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result
