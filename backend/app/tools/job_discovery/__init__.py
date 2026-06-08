from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Protocol
from urllib.parse import urlparse

from app.repositories.job_repository import JobRepository


EXTERNAL_SOURCES = {"ashby", "greenhouse", "lever"}
LOW_CONFIDENCE_THRESHOLD = 0.55
CHINA_CITY_TERMS = {
    "北京",
    "上海",
    "深圳",
    "广州",
    "杭州",
    "成都",
    "南京",
    "武汉",
    "西安",
    "苏州",
    "重庆",
    "天津",
    "厦门",
    "长沙",
    "中国",
}
CHINA_COMPANY_TERMS = {
    "字节",
    "腾讯",
    "阿里",
    "蚂蚁",
    "美团",
    "小红书",
    "滴滴",
    "京东",
    "网易",
    "拼多多",
    "快手",
    "知乎",
    "中金",
    "华泰",
    "招商",
    "易方达",
    "德勤",
    "普华永道",
}


@dataclass(frozen=True)
class JobDiscoveryFilters:
    city: str | None = None
    experience: str | None = None
    skills: tuple[str, ...] = ()


@dataclass(frozen=True)
class TitleTaxonomy:
    function: str
    canonical_title: str
    specialization: str | None
    canonical_confidence: float


@dataclass(frozen=True)
class JobSearchCandidate:
    id: str
    raw_title: str
    company: str
    city: str | None
    source: str
    url: str | None
    summary: str | None
    salary: str | None
    duration: str | None
    deadline: date | None
    canonical_title: str | None = None
    function: str | None = None
    specialization: str | None = None
    canonical_confidence: float | None = None
    employment_type: str | None = None
    posted_at: datetime | None = None
    last_seen_at: datetime | None = None
    is_active: bool | None = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class JobSearchResult:
    candidates: list[JobSearchCandidate]
    query_expansions: list[str]


class SearchJobs(Protocol):
    def search_jobs(self, *, keyword: str | None, filters: JobDiscoveryFilters) -> JobSearchResult:
        """Search externally sourced job data and return normalized candidates."""


class RepositoryJobSearcher:
    """Search the synchronized external job table through a small replaceable interface."""

    def __init__(self, job_repository: JobRepository):
        self.job_repository = job_repository

    def search_jobs(self, *, keyword: str | None, filters: JobDiscoveryFilters) -> JobSearchResult:
        query_expansions = expand_job_queries(keyword)
        seen_ids: set[str] = set()
        candidates: list[JobSearchCandidate] = []

        if query_expansions:
            raw_jobs = []
            for query in query_expansions:
                raw_jobs.extend(self.job_repository.list_active_jobs(keyword=query))
        else:
            raw_jobs = self.job_repository.list_active_jobs()

        for job in raw_jobs:
            job_id = str(job.id)
            if job_id in seen_ids:
                continue
            seen_ids.add(job_id)
            parsed = job.jd_parsed or {}
            taxonomy = classify_title(job.title)
            candidate = JobSearchCandidate(
                id=job_id,
                raw_title=job.title,
                canonical_title=taxonomy.canonical_title,
                function=taxonomy.function,
                specialization=taxonomy.specialization,
                canonical_confidence=taxonomy.canonical_confidence,
                company=job.company,
                city=job.city,
                source=job.source,
                url=job.apply_url,
                summary=job.jd_text,
                salary=job.salary_range,
                duration=job.duration,
                deadline=job.deadline,
                employment_type=parsed.get("employment_type") if isinstance(parsed, dict) else None,
                posted_at=_parse_datetime(parsed.get("posted_at")) if isinstance(parsed, dict) else None,
                last_seen_at=job.crawled_at,
                is_active=job.is_active,
                metadata=parsed if isinstance(parsed, dict) else {},
            )
            # 岗位发现优先回答“市场上有哪些具体 title”，不能因为 JD 里出现 product 就把无关岗位混进来。
            if query_expansions and not _matches_title_query(candidate, query_expansions):
                continue
            if _matches_filters(candidate, filters):
                candidates.append(candidate)

        return JobSearchResult(candidates=candidates, query_expansions=query_expansions)


def expand_job_queries(keyword: str | None) -> list[str]:
    base = (keyword or "").strip()
    if not base:
        return []

    lowered = base.lower()
    expansions: list[str] = [base]
    if "ai pm" in lowered or ("ai" in lowered and ("product" in lowered or "产品" in base)):
        expansions.extend(["AI Product Manager", "AI PM", "AI 产品经理", "LLM Product", "Product Manager", "产品经理"])
    elif "产品" in base or "product" in lowered or lowered == "pm":
        expansions.extend(["产品", "Product", "Product Manager", "Associate Product Manager", "Product Intern", "Growth Product", "产品经理", "产品运营", "增长产品"])
    elif "后端" in base or "backend" in lowered:
        expansions.extend(["后端", "Backend", "Backend Engineer", "Java Backend Engineer", "Golang Backend Engineer", "Platform Engineer", "Python"])
    elif "数据" in base or "data" in lowered:
        expansions.extend(["数据", "Data", "Data Analyst", "Analytics", "Business Analyst", "SQL"])
    elif "咨询" in base or "consult" in lowered:
        expansions.extend(["咨询", "Consulting", "Business Analyst", "Strategy", "Research"])
    elif "金融" in base or "finance" in lowered:
        expansions.extend(["金融", "Finance", "Investment", "Risk", "Analyst"])

    return _unique([item for item in expansions if item.strip()])


def aggregate_discovered_jobs(
    candidates: list[JobSearchCandidate],
    *,
    filters: JobDiscoveryFilters | None = None,
    query_expansions: list[str] | None = None,
) -> dict:
    filters = filters or JobDiscoveryFilters()
    deduped: dict[str, JobSearchCandidate] = {}
    dedupe_counts: dict[str, int] = {}
    dedupe_sources: dict[str, set[str]] = {}
    for candidate in candidates:
        key = _dedupe_key(candidate)
        dedupe_counts[key] = dedupe_counts.get(key, 0) + 1
        dedupe_sources.setdefault(key, set()).add(candidate.source)
        if key not in deduped or _recency_score(candidate) > _recency_score(deduped[key]):
            deduped[key] = candidate

    grouped = list(deduped.items())
    cluster_counts: dict[str, int] = {}
    cluster_companies: dict[str, set[str]] = {}
    for key, candidate in grouped:
        taxonomy = _candidate_taxonomy(candidate)
        canonical = taxonomy.canonical_title if taxonomy.canonical_confidence >= LOW_CONFIDENCE_THRESHOLD else candidate.raw_title.strip()
        cluster_counts[canonical] = cluster_counts.get(canonical, 0) + 1
        cluster_companies.setdefault(canonical, set()).add(_normalize_company(candidate.company))

    max_frequency = max(cluster_counts.values(), default=1)
    max_company_coverage = max((len(companies) for companies in cluster_companies.values()), default=1)
    jobs: list[dict[str, Any]] = []
    for key, candidate in grouped:
        taxonomy = _candidate_taxonomy(candidate)
        canonical = taxonomy.canonical_title if taxonomy.canonical_confidence >= LOW_CONFIDENCE_THRESHOLD else candidate.raw_title.strip()
        skills = extract_skills(" ".join([candidate.raw_title, candidate.summary or ""]))
        if filters.skills and not set(_normalize_skill_list(filters.skills)).issubset(set(skills)):
            continue
        frequency = cluster_counts.get(canonical, 1)
        source_diversity = len(dedupe_sources.get(key, {candidate.source}))
        company_coverage = len(cluster_companies.get(canonical, {candidate.company}))
        recency_score = _recency_score(candidate)
        popularity_score = _popularity_score(
            frequency=frequency,
            max_frequency=max_frequency,
            source_diversity=source_diversity,
            company_coverage=company_coverage,
            max_company_coverage=max_company_coverage,
            recency_score=recency_score,
        )
        job = {
            "id": candidate.id,
            "title": candidate.raw_title,
            "raw_title": candidate.raw_title,
            "canonical_title": canonical,
            "function": taxonomy.function,
            "specialization": taxonomy.specialization,
            "canonical_confidence": taxonomy.canonical_confidence,
            "low_confidence": taxonomy.canonical_confidence < LOW_CONFIDENCE_THRESHOLD,
            "city": candidate.city,
            "experience": infer_experience(candidate.raw_title, candidate.summary),
            "employment_type": candidate.employment_type,
            "job_type": infer_job_type(candidate.raw_title, candidate.summary, candidate.employment_type),
            "job_type_label": job_type_label(infer_job_type(candidate.raw_title, candidate.summary, candidate.employment_type)),
            "market_region": infer_market_region(company=candidate.company, city=candidate.city, url=candidate.url),
            "skills": skills,
            "company": candidate.company,
            "source": candidate.source,
            "url": candidate.url,
            "apply_url": candidate.url,
            "summary": _summarize(candidate.summary),
            "jd_text": candidate.summary,
            "salary": candidate.salary,
            "duration": candidate.duration,
            "deadline": candidate.deadline.isoformat() if candidate.deadline else None,
            "posted_at": _iso_datetime(candidate.posted_at),
            "last_seen_at": _iso_datetime(candidate.last_seen_at),
            "is_active": candidate.is_active if candidate.is_active is not None else True,
            "popularity_score": popularity_score,
            "recency_score": round(recency_score, 3),
            "cluster_frequency": frequency,
            "source_frequency": dedupe_counts.get(key, 1),
            "rag_payload": {},
        }
        job["rag_payload"] = _rag_payload(candidate=candidate, job=job)
        jobs.append(job)

    jobs.sort(
        key=lambda item: (
            0 if item.get("market_region") == "CN" else 1,
            -float(item.get("popularity_score") or 0),
            -float(item.get("recency_score") or 0),
            str(item.get("canonical_title") or ""),
            str(item.get("company") or ""),
            str(item.get("raw_title") or ""),
        )
    )
    source_kind = _source_kind([candidate for _, candidate in grouped])
    fallback_notice = _fallback_notice(source_kind=source_kind, total=len(jobs))

    return {
        "total": len(jobs),
        "page": 1,
        "source_kind": source_kind,
        "fallback_notice": fallback_notice,
        "query_expansions": query_expansions or [],
        "jobs": jobs,
        "taxonomy": sorted(cluster_counts.items(), key=lambda item: item[1], reverse=True),
    }


def classify_title(raw_title: str) -> TitleTaxonomy:
    title = _normalize_text(raw_title)
    is_intern = _title_is_intern(title)

    if ("ai" in title or "llm" in title or "大模型" in title) and ("product" in title or "pm" in title or "产品" in title):
        return TitleTaxonomy("Product", "AI Product Manager Intern" if is_intern else "AI Product Manager", "LLM", 0.92)
    if "data product" in title or "数据产品" in title:
        return TitleTaxonomy("Product", "数据产品实习生" if is_intern else "数据产品经理", "Data", 0.88)
    if any(token in title for token in ["product operations", "growth product", "产品运营", "增长产品", "商业产品"]):
        return TitleTaxonomy("Product", "产品运营实习生" if is_intern else "产品运营", "Growth" if "growth" in title or "增长" in title else "Operations", 0.86)
    if any(token in title for token in ["associate product manager", "product manager", "product intern", "apm", "产品经理", "产品实习"]):
        return TitleTaxonomy("Product", "产品经理实习生" if is_intern else "产品经理", None, 0.84)

    if "java" in title and any(token in title for token in ["backend", "back-end", "后端", "服务端", "研发"]):
        return TitleTaxonomy("Engineering", "Java Backend Engineer Intern" if is_intern else "Java Backend Engineer", "Java", 0.9)
    if any(token in title for token in ["golang", " go ", "go后端", "go 后端"]):
        return TitleTaxonomy("Engineering", "Golang Backend Engineer Intern" if is_intern else "Golang Backend Engineer", "Golang", 0.88)
    if any(token in title for token in ["distributed systems", "分布式"]):
        return TitleTaxonomy("Engineering", "Distributed Systems Engineer", "Distributed Systems", 0.86)
    if any(token in title for token in ["platform engineer", "平台"]):
        return TitleTaxonomy("Engineering", "Platform Backend Engineer", "Platform", 0.82)
    if any(token in title for token in ["backend", "back-end", "server", "后端", "服务端"]):
        return TitleTaxonomy("Engineering", "Backend Engineer Intern" if is_intern else "Backend Engineer", None, 0.78)
    if any(token in title for token in ["frontend", "front-end", "react", "next.js", "前端"]):
        return TitleTaxonomy("Engineering", "Frontend Engineer Intern" if is_intern else "Frontend Engineer", "Frontend", 0.8)
    if any(token in title for token in ["software engineer", "swe intern", "软件开发", "研发实习"]):
        return TitleTaxonomy("Engineering", "软件开发实习生" if is_intern else "软件开发工程师", None, 0.72)

    if any(token in title for token in ["data analyst", "analytics", "business analyst", "数据分析", "商业分析"]):
        return TitleTaxonomy("Data", "数据分析实习生" if is_intern else "数据分析师", "Analytics", 0.84)
    if any(token in title for token in ["machine learning", "algorithm", "算法", "推荐策略"]):
        return TitleTaxonomy("AI", "算法实习生" if is_intern else "算法工程师", "Machine Learning", 0.82)
    if any(token in title for token in ["consulting", "strategy analyst", "management consultant", "咨询"]):
        return TitleTaxonomy("Consulting", "咨询分析实习生" if is_intern else "咨询分析师", "Strategy", 0.82)
    if any(token in title for token in ["investment", "finance", "risk", "equity research", "投行", "行业研究", "风控"]):
        return TitleTaxonomy("Finance", "金融分析实习生" if is_intern else "金融分析师", "Finance", 0.82)

    return TitleTaxonomy("Other", raw_title.strip(), None, 0.35)


def canonicalize_title(raw_title: str) -> str:
    taxonomy = classify_title(raw_title)
    return taxonomy.canonical_title if taxonomy.canonical_confidence >= LOW_CONFIDENCE_THRESHOLD else raw_title.strip()


def infer_experience(raw_title: str, summary: str | None = None) -> str:
    title_text = _normalize_text(raw_title)
    if _title_is_intern(title_text):
        return "intern"
    if any(token in title_text for token in ["校招", "应届"]) or re.search(r"\b(new grad|entry|junior|associate)\b", title_text):
        return "entry"
    if any(token in title_text for token in ["资深", "专家"]) or re.search(r"\b(senior|staff|principal|lead|sr)\.?\b", title_text):
        return "senior"
    return "unspecified"


def infer_job_type(raw_title: str, summary: str | None = None, employment_type: str | None = None) -> str:
    text = _normalize_text(" ".join([raw_title, summary or "", employment_type or ""]))
    if any(token in text for token in ["实习", "intern", "internship", "campus"]):
        return "intern"
    if any(token in text for token in ["正式", "全职", "社招", "full-time", "full time", "permanent"]):
        return "full_time"
    return "unspecified"


def job_type_label(job_type: str | None) -> str:
    if job_type == "intern":
        return "实习"
    if job_type == "full_time":
        return "正式"
    return "未注明"


def infer_market_region(*, company: str | None, city: str | None, url: str | None) -> str:
    text = " ".join([company or "", city or "", url or ""]).lower()
    if any("\u4e00" <= char <= "\u9fff" for char in text):
        return "CN"
    if any(term.lower() in text for term in CHINA_CITY_TERMS | CHINA_COMPANY_TERMS):
        return "CN"
    if any(domain in text for domain in ["bytedance", "meituan", "qq.com", "tencent", "alibaba", "antgroup", "jd.com", "xiaohongshu", "pinduoduo", "kuaishou"]):
        return "CN"
    return "GLOBAL"


def recommend_jobs(
    jobs: list[dict[str, Any]],
    *,
    resume_profile: dict[str, Any] | None = None,
    city: str | None = None,
    experience: str | None = None,
    skills: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    recommended = [score_job_match(job, resume_profile=resume_profile or {}, city=city, experience=experience, skills=skills) for job in jobs]
    recommended.sort(
        key=lambda item: (
            -float(item.get("recommendation_score") or 0),
            -float(item.get("popularity_score") or 0),
            -float(item.get("recency_score") or 0),
        )
    )
    return recommended


def score_job_match(
    job: dict[str, Any],
    *,
    resume_profile: dict[str, Any],
    city: str | None = None,
    experience: str | None = None,
    skills: tuple[str, ...] = (),
) -> dict[str, Any]:
    resume_skills = set(_normalize_skill_list(tuple(resume_profile.get("skills") or ())))
    requested_skills = set(_normalize_skill_list(skills))
    job_skills = set(job.get("skills") or [])
    required_skills = job_skills or requested_skills
    matched_skills = sorted(resume_skills & required_skills)
    missing_skills = sorted(required_skills - resume_skills)

    skill_match_score = round(len(matched_skills) / max(len(required_skills), 1), 2) if required_skills else 0.6
    experience_match_score = _experience_match_score(job.get("experience"), experience)
    city_match_score = _city_match_score(job.get("city"), city)
    relevance_score = round((skill_match_score * 0.5) + (experience_match_score * 0.2) + (city_match_score * 0.15) + (float(job.get("recency_score") or 0.6) * 0.15), 2)
    popularity_component = min(float(job.get("popularity_score") or 0) / 100.0, 1.0)
    recommendation_score = round((relevance_score * 0.7) + (popularity_component * 0.2) + (float(job.get("recency_score") or 0.6) * 0.1), 2)

    scored = dict(job)
    scored.update(
        {
            "recommendation_score": recommendation_score,
            "relevance_score": relevance_score,
            "skill_match_score": skill_match_score,
            "experience_match_score": experience_match_score,
            "city_match_score": city_match_score,
            "matched_skills": matched_skills,
            "missing_skills": missing_skills,
            "matched_experience": job.get("experience") if experience_match_score >= 0.8 else None,
            "missing_experience": None if experience_match_score >= 0.8 else experience,
            "strengths": _strengths(matched_skills=matched_skills, job=job),
            "risks": _risks(missing_skills=missing_skills, job=job),
            "suggested_resume_improvements": _resume_improvements(missing_skills=missing_skills, job=job),
            "application_priority": _application_priority(recommendation_score),
        }
    )
    scored["explanation"] = explain_job_match(scored)
    scored["score_dimensions"] = _job_score_dimensions(
        job=scored,
        resume_profile=resume_profile,
        matched_skills=matched_skills,
        missing_skills=missing_skills,
        skill_match_score=skill_match_score,
        experience_match_score=experience_match_score,
        city_match_score=city_match_score,
    )
    scored["evidence_summary"] = _job_evidence_summary(job=scored, resume_profile=resume_profile)
    return scored


def explain_job_match(job: dict[str, Any]) -> str:
    matched = "、".join(job.get("matched_skills") or []) or "暂未命中明显技能"
    missing = "、".join(job.get("missing_skills") or []) or "主要技能缺口不明显"
    return (
        f"推荐分 {int(round(float(job.get('recommendation_score') or 0) * 100))}："
        f"该岗位偏 {job.get('canonical_title') or job.get('raw_title')}，已匹配 {matched}；"
        f"需要补强 {missing}。建议按 {job.get('application_priority')} 优先级处理。"
    )


def _job_score_dimensions(
    *,
    job: dict[str, Any],
    resume_profile: dict[str, Any],
    matched_skills: list[str],
    missing_skills: list[str],
    skill_match_score: float,
    experience_match_score: float,
    city_match_score: float,
) -> list[dict[str, Any]]:
    return [
        _score_dimension(
            dimension="技能匹配",
            score=skill_match_score,
            weight=0.50,
            evidence=[f"简历技能命中：{'、'.join(matched_skills) or '暂无'}", f"岗位要求技能：{'、'.join(job.get('skills') or []) or '未结构化'}"],
            problems=[f"缺少 {skill} 证据" for skill in missing_skills[:3]],
            suggestions=_resume_improvements(missing_skills=missing_skills, job=job),
            confidence=0.84 if job.get("skills") else 0.62,
        ),
        _score_dimension(
            dimension="经验匹配",
            score=experience_match_score,
            weight=0.20,
            evidence=[f"岗位经验要求：{job.get('experience') or '未注明'}"],
            problems=[] if experience_match_score >= 0.8 else ["经验要求不完全匹配或岗位未注明"],
            suggestions=["在简历摘要中明确实习/项目年限和本人负责模块"],
            confidence=0.72,
        ),
        _score_dimension(
            dimension="城市匹配",
            score=city_match_score,
            weight=0.15,
            evidence=[f"岗位城市：{job.get('city') or '未注明'}"],
            problems=[] if city_match_score >= 0.8 else ["城市与当前筛选条件不完全一致"],
            suggestions=["确认是否接受异地、远程或通勤安排"],
            confidence=0.8,
        ),
        _score_dimension(
            dimension="时效与热度",
            score=round((float(job.get("recency_score") or 0.6) + min(float(job.get("popularity_score") or 0) / 100.0, 1.0)) / 2, 2),
            weight=0.15,
            evidence=[f"热度 {job.get('popularity_score') or 0}", f"最近出现 {job.get('last_seen_at') or '未知'}"],
            problems=[] if job.get("is_active", True) else ["岗位疑似失效"],
            suggestions=["投递前打开原站确认岗位仍开放"],
            confidence=0.7,
        ),
    ]


def _score_dimension(
    *,
    dimension: str,
    score: float,
    weight: float,
    evidence: list[str],
    problems: list[str],
    suggestions: list[str],
    confidence: float,
) -> dict[str, Any]:
    return {
        "dimension": dimension,
        "score": round(max(0.0, min(1.0, float(score))), 2),
        "weight": weight,
        "evidence": [item for item in evidence if item][:4],
        "problems": [item for item in problems if item][:4],
        "suggestions": [item for item in suggestions if item][:4],
        "confidence": round(max(0.0, min(1.0, confidence)), 2),
    }


def _job_evidence_summary(*, job: dict[str, Any], resume_profile: dict[str, Any]) -> dict[str, Any]:
    resume_projects = resume_profile.get("projects") or []
    project_names = [str(item.get("name") or "") for item in resume_projects if isinstance(item, dict) and item.get("name")]
    return {
        "resume_evidence": [
            f"简历技能：{'、'.join(list(resume_profile.get('skills') or [])[:6]) or '未提供'}",
            f"相关项目：{'、'.join(project_names[:3]) or '未提供'}",
        ],
        "job_requirement": [
            f"岗位标题：{job.get('raw_title') or job.get('title')}",
            f"岗位技能：{'、'.join(job.get('skills') or []) or '未结构化'}",
        ],
        "supports": f"推荐依据来自简历技能/项目与 JD 技能、城市、经验、时效的交叉匹配。",
    }


def _title_is_intern(title: str) -> bool:
    return "实习" in title or re.search(r"\b(intern|internship|campus)\b", title) is not None


def extract_skills(text: str) -> list[str]:
    normalized = _normalize_text(text)
    skill_patterns = {
        "SQL": ["sql"],
        "Python": ["python"],
        "FastAPI": ["fastapi"],
        "Redis": ["redis"],
        "React": ["react"],
        "Next.js": ["next.js", "nextjs"],
        "TypeScript": ["typescript", "ts "],
        "Java": ["java"],
        "Go": ["golang", " go ", "go后端", "go 后端"],
        "Docker": ["docker"],
        "Kubernetes": ["kubernetes", "k8s"],
        "Excel": ["excel"],
        "PPT": ["ppt", "powerpoint"],
        "Tableau": ["tableau"],
        "Power BI": ["power bi"],
        "A/B Testing": ["a/b", "ab test", "experiment", "实验", "测试"],
        "User Research": ["user research", "用户研究", "用户访谈"],
        "Data Analysis": ["data analysis", "analytics", "数据分析", "指标"],
        "Product Strategy": ["roadmap", "strategy", "产品策略", "需求分析"],
        "Communication": ["communication", "stakeholder", "沟通", "协作"],
        "LLM": ["llm", "大模型", "generative ai", "ai product"],
    }
    skills: list[str] = []
    for skill, patterns in skill_patterns.items():
        if any(pattern in normalized for pattern in patterns):
            skills.append(skill)
    return skills


def _candidate_taxonomy(candidate: JobSearchCandidate) -> TitleTaxonomy:
    if candidate.canonical_title and candidate.function and candidate.canonical_confidence is not None:
        return TitleTaxonomy(
            function=candidate.function,
            canonical_title=candidate.canonical_title,
            specialization=candidate.specialization,
            canonical_confidence=candidate.canonical_confidence,
        )
    return classify_title(candidate.raw_title)


def _matches_filters(candidate: JobSearchCandidate, filters: JobDiscoveryFilters) -> bool:
    if filters.city and filters.city.lower() not in (candidate.city or "").lower():
        return False
    expected_experience = _normalize_experience(filters.experience)
    if expected_experience and infer_experience(candidate.raw_title, candidate.summary) != expected_experience:
        return False
    return True


def _matches_title_query(candidate: JobSearchCandidate, query_expansions: list[str]) -> bool:
    taxonomy = _candidate_taxonomy(candidate)
    title_text = _normalize_text(" ".join([candidate.raw_title, taxonomy.canonical_title, taxonomy.function, taxonomy.specialization or ""]))
    return any(_normalize_text(query) in title_text for query in query_expansions if query.strip())


def _source_kind(candidates: list[JobSearchCandidate]) -> str:
    sources = {candidate.source for candidate in candidates}
    if sources & EXTERNAL_SOURCES:
        return "external_synced"
    if sources:
        return "local_seed"
    return "empty"


def _fallback_notice(*, source_kind: str, total: int) -> str | None:
    if source_kind == "external_synced":
        return None
    if total == 0:
        return "未命中真实招聘数据源。当前没有使用模型编造岗位，请先同步 Ashby/Greenhouse 或接入网页检索。"
    return "当前未命中 Ashby/Greenhouse 等真实 ATS 岗位，结果来自本地种子或手工数据，不是实时市场全集。"


def _rag_payload(*, candidate: JobSearchCandidate, job: dict[str, Any]) -> dict:
    metadata = {
        "raw_title": job.get("raw_title"),
        "canonical_title": job.get("canonical_title"),
        "function": job.get("function"),
        "specialization": job.get("specialization"),
        "canonical_confidence": job.get("canonical_confidence"),
        "company": job.get("company"),
        "city": job.get("city"),
        "source": job.get("source"),
        "url": job.get("url"),
        "skills": job.get("skills") or [],
        "experience": job.get("experience"),
        "job_type": job.get("job_type"),
        "job_type_label": job.get("job_type_label"),
        "market_region": job.get("market_region"),
        "posted_at": job.get("posted_at"),
        "last_seen_at": job.get("last_seen_at"),
        "is_active": job.get("is_active"),
        "popularity_score": job.get("popularity_score"),
    }
    return {
        "document_id": _stable_document_id(candidate),
        "text": "\n".join(
            filter(
                None,
                [
                    f"Title: {job.get('raw_title')}",
                    f"Canonical: {job.get('canonical_title')}",
                    f"Function: {job.get('function')}",
                    f"Company: {job.get('company')}",
                    f"City: {job.get('city')}",
                    f"Skills: {', '.join(job.get('skills') or [])}",
                    f"Description: {job.get('jd_text') or ''}",
                ],
            )
        ),
        "metadata": metadata,
    }


def _dedupe_key(candidate: JobSearchCandidate) -> str:
    taxonomy = _candidate_taxonomy(candidate)
    company = _normalize_company(candidate.company)
    title = _normalize_text(taxonomy.canonical_title if taxonomy.canonical_confidence >= LOW_CONFIDENCE_THRESHOLD else candidate.raw_title)
    city = _normalize_text(candidate.city or "")
    employment = _normalize_text(candidate.employment_type or infer_experience(candidate.raw_title, candidate.summary))
    fingerprint = _url_fingerprint(candidate.url)
    return "|".join([company, title, city, employment, fingerprint])


def _stable_document_id(candidate: JobSearchCandidate) -> str:
    return f"job:{candidate.source}:{_slug(_dedupe_key(candidate))}"


def _url_fingerprint(url: str | None) -> str:
    if not url:
        return "no-url"
    parsed = urlparse(url.lower())
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return parsed.netloc
    tail = re.sub(r"[^a-z0-9\u4e00-\u9fff-]", "", parts[-1])
    return tail or parsed.netloc


def _normalize_company(company: str) -> str:
    text = _normalize_text(company)
    text = re.sub(r"\b(inc|ltd|llc|co|corp|corporation)\b\.?", "", text)
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", text).strip()


def _recency_score(candidate: JobSearchCandidate) -> float:
    if candidate.is_active is False:
        return 0.05
    reference = candidate.last_seen_at or candidate.posted_at
    if reference is None:
        return 0.65
    if reference.tzinfo is not None:
        reference = reference.replace(tzinfo=None)
    days = max((datetime.utcnow() - reference).days, 0)
    return max(0.08, 1 / (1 + days / 45))


def _popularity_score(*, frequency: int, max_frequency: int, source_diversity: int, company_coverage: int, max_company_coverage: int, recency_score: float) -> int:
    frequency_score = frequency / max(max_frequency, 1)
    source_score = min(source_diversity / 3, 1)
    company_score = company_coverage / max(max_company_coverage, 1)
    score = (frequency_score * 0.45) + (source_score * 0.2) + (company_score * 0.15) + (recency_score * 0.2)
    return int(round(min(max(score, 0), 1) * 100))


def _experience_match_score(job_experience: str | None, wanted: str | None) -> float:
    normalized = _normalize_experience(wanted)
    if not normalized:
        return 0.75
    if job_experience == normalized:
        return 1.0
    if job_experience == "unspecified":
        return 0.65
    return 0.35


def _city_match_score(job_city: str | None, wanted_city: str | None) -> float:
    if not wanted_city:
        return 0.75
    if job_city and wanted_city.lower() in job_city.lower():
        return 1.0
    if job_city and "remote" in job_city.lower():
        return 0.8
    return 0.35


def _application_priority(score: float) -> str:
    if score >= 0.78:
        return "high"
    if score >= 0.58:
        return "medium"
    return "low"


def _strengths(*, matched_skills: list[str], job: dict[str, Any]) -> list[str]:
    strengths = [f"已匹配 {skill}" for skill in matched_skills[:3]]
    if job.get("city_match_score") == 1.0:
        strengths.append("城市匹配")
    return strengths or ["岗位方向与当前目标有一定相关性"]


def _risks(*, missing_skills: list[str], job: dict[str, Any]) -> list[str]:
    risks = [f"缺少 {skill} 证据" for skill in missing_skills[:3]]
    if float(job.get("recency_score") or 0) < 0.3:
        risks.append("岗位较旧，需要确认是否仍开放")
    return risks or ["暂无明显硬性缺口"]


def _resume_improvements(*, missing_skills: list[str], job: dict[str, Any]) -> list[str]:
    if not missing_skills:
        return ["在简历项目中补充该岗位相关的量化结果"]
    return [f"补一条能证明 {skill} 的项目或指标" for skill in missing_skills[:3]]


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _iso_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.replace(tzinfo=None)
    return value.isoformat()


def _normalize_experience(value: str | None) -> str | None:
    text = _normalize_text(value or "")
    if not text:
        return None
    if text in {"intern", "实习", "internship"}:
        return "intern"
    if text in {"entry", "junior", "校招", "应届"}:
        return "entry"
    if text in {"senior", "资深", "专家"}:
        return "senior"
    return text


def _normalize_skill_list(skills: tuple[str, ...]) -> list[str]:
    wanted: list[str] = []
    for skill in skills:
        wanted.extend(extract_skills(skill) or [skill.strip()])
    return _unique([item for item in wanted if item])


def _summarize(value: str | None) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    return text[:320]


def _normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").lower()).strip()


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", value).strip("-").lower()
    return slug[:120] or "unknown"


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
