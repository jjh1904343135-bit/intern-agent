from __future__ import annotations

from typing import Any

from app.repositories.application_repository import ApplicationRepository
from app.repositories.job_repository import JobRepository
from app.repositories.resume_repository import ResumeRepository
from app.services.application_service import ApplicationService
from app.services.job_service import JobService
from app.services.knowledge_rag_service import KnowledgeRagService
from app.tools.job_discovery import extract_skills


class ChatToolExecutor:
    """Adapter that exposes business services as chat-agent tool results."""

    def __init__(self, *, db) -> None:
        self.db = db

    def run(self, *, user_id: str, intent: str, message: str, tools: list[str]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if "resume_profile" in tools:
            result["resume_profile"] = self.resume_profile(user_id=user_id)
        if "job_search" in tools:
            result["job_search"] = self.job_search(user_id=user_id, message=message)
        if "application_list" in tools:
            result["application_list"] = self.application_list(user_id=user_id)
        if "knowledge_search" in tools:
            result["knowledge_search"] = self.knowledge_search(message=message)
        return result

    def knowledge_search(self, *, message: str) -> dict[str, Any]:
        return KnowledgeRagService(self.db).search(message, limit=5, min_score=0.2)

    def resume_profile(self, *, user_id: str) -> dict[str, Any]:
        resume = ResumeRepository(self.db).get_default_by_user_id(user_id=user_id)
        if resume is None:
            return {"available": False, "score": None, "risks": []}
        score = resume.score_report or {}
        return {
            "available": True,
            "file_name": resume.file_name,
            "parse_status": resume.parse_status,
            "score": score.get("overall_score"),
            "risks": list(score.get("risks") or [])[:3],
            "skills": list((resume.parsed_content or {}).get("skills") or [])[:8],
        }

    def job_search(self, *, user_id: str, message: str) -> dict[str, Any]:
        keyword = keyword_from_message(message)
        city = city_from_message(message)
        experience = "intern" if any(token in message.lower() for token in ["瀹炰範", "intern"]) else None
        skills = tuple(extract_skills(message))
        service = JobService(JobRepository(self.db), ResumeRepository(self.db))
        try:
            payload = service.discover_jobs(user_id=user_id, keyword=keyword, city=city, experience=experience, skills=skills)
        except Exception:
            payload = service.discover_jobs(user_id=None, keyword=keyword, city=city, experience=experience, skills=skills)
        jobs = payload.get("jobs", [])[:8]
        return {
            "total": payload.get("total", 0),
            "keyword": keyword,
            "city": city,
            "experience": experience,
            "skills": list(skills),
            "source_kind": payload.get("source_kind"),
            "fallback_notice": payload.get("fallback_notice"),
            "query_expansions": payload.get("query_expansions", []),
            "top_titles": [
                f"{job.get('company')} {job.get('raw_title')} -> {job.get('canonical_title')} popularity={job.get('popularity_score')}"
                for job in jobs
            ],
            "jobs": [
                {
                    "raw_title": job.get("raw_title"),
                    "canonical_title": job.get("canonical_title"),
                    "function": job.get("function"),
                    "specialization": job.get("specialization"),
                    "city": job.get("city"),
                    "experience": job.get("experience"),
                    "skills": job.get("skills", []),
                    "company": job.get("company"),
                    "source": job.get("source"),
                    "url": job.get("url"),
                    "summary": job.get("summary"),
                    "popularity_score": job.get("popularity_score"),
                    "recommendation_score": job.get("recommendation_score"),
                    "score_dimensions": job.get("score_dimensions", []),
                    "evidence_summary": job.get("evidence_summary", {}),
                    "explanation": job.get("explanation"),
                    "matched_skills": job.get("matched_skills", []),
                    "missing_skills": job.get("missing_skills", []),
                    "application_priority": job.get("application_priority"),
                }
                for job in jobs
            ],
            "apply_urls": [job.get("url") or job.get("apply_url") for job in jobs if job.get("url") or job.get("apply_url")],
        }

    def application_list(self, *, user_id: str) -> dict[str, Any]:
        service = ApplicationService(
            ApplicationRepository(self.db),
            JobRepository(self.db),
            ResumeRepository(self.db),
        )
        payload = service.list_applications(user_id=user_id)
        statuses: dict[str, int] = {}
        for item in payload.get("items", []):
            statuses[item.get("status", "unknown")] = statuses.get(item.get("status", "unknown"), 0) + 1
        return {"total": payload.get("total", 0), "statuses": statuses}


def keyword_from_message(message: str) -> str | None:
    lowered = message.lower()
    terms: list[str] = []
    keyword_rules = [
        ("腾讯", ("腾讯", "tencent")),
        ("阿里", ("阿里", "alibaba")),
        ("字节", ("字节", "bytedance", "抖音")),
        ("美团", ("美团", "meituan")),
        ("百度", ("百度", "baidu")),
        ("京东", ("京东", "jd")),
        ("网易", ("网易", "netease")),
        ("小米", ("小米", "xiaomi")),
        ("快手", ("快手", "kuaishou")),
        ("华为", ("华为", "huawei")),
        ("Java", ("java",)),
        ("后端", ("后端", "backend", "服务端", "开发岗")),
        ("开发", ("开发", "工程师")),
        ("前端", ("前端", "frontend", "react", "next.js")),
        ("算法", ("算法", "机器学习", "推荐", "搜索", "llm", "ai")),
        ("产品", ("产品", "product", "pm")),
        ("数据", ("数据", "data", "sql")),
        ("测试", ("测试", "qa", "test")),
        ("咨询", ("咨询", "consult")),
    ]
    for label, tokens in keyword_rules:
        if any(token in lowered for token in tokens):
            terms.append(label)
    return " ".join(dict.fromkeys(terms)) or None


def city_from_message(message: str) -> str | None:
    for city in ["北京", "上海", "深圳", "杭州", "广州", "成都", "Remote", "San Francisco", "Singapore"]:
        if city.lower() in message.lower():
            return city
    return None
