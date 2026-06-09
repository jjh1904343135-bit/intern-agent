"""岗位业务编排层。

这里负责把岗位搜索、外部同步、推荐评分和解释结果组织成业务接口。
岗位来源 adapter、标题分类和技能抽取在工具层；数据库读写在 repository；
这个 service 只做求职业务流程的组合与兜底。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.core.settings import settings
from app.repositories.job_repository import JobRepository
from app.repositories.resume_repository import ResumeRepository
from app.scripts.sync_real_jobs import sync_real_jobs
from app.tools.embeddings.fastembed_adapter import embed_text
from app.tools.job_discovery import (
    JobDiscoveryFilters,
    RepositoryJobSearcher,
    aggregate_discovered_jobs,
    classify_title,
    extract_skills,
    infer_experience,
    infer_job_type,
    infer_market_region,
    job_type_label,
    recommend_jobs,
)
from app.tools.job_sources import default_source_statuses, fetch_liepin_mcp_jobs, fetch_tencent_jobs
from app.tools.retrievers.qdrant_retriever import search_similar_jobs


@dataclass
class JobServiceError(Exception):
    status_code: int
    code: int
    message: str


@dataclass(frozen=True)
class JobSearchIntent:
    company: str | None
    role_keyword: str


class JobService:
    """提供岗位发现、推荐解释和外部岗位同步的业务服务。"""

    def __init__(self, job_repository: JobRepository, resume_repository: ResumeRepository):
        self.job_repository = job_repository
        self.resume_repository = resume_repository

    def search_jobs(
        self,
        *,
        user_id: str | None = None,
        match_resume: bool = False,
        keyword: str | None = None,
        city: str | None = None,
        limit: int = 30,
    ) -> dict:
        limit = max(1, min(int(limit or 30), 100))
        source_status = default_source_statuses()
        jobs = self._load_ranked_jobs(keyword=keyword, city=city)
        deduped_entries = self._dedupe_jobs(jobs)
        deduped_entries.sort(key=lambda entry: self._entry_sort_key(entry, keyword=keyword))

        refresh_status = self._refresh_tencent_official_if_company_query(
            keyword=keyword,
            city=city,
            current_entries=deduped_entries,
            limit=limit,
        )
        if refresh_status is not None:
            source_status["tencent_official"] = refresh_status
            if refresh_status.get("status") == "ok" and int(refresh_status.get("records") or 0) > 0:
                jobs = self._load_ranked_jobs(keyword=keyword, city=city)
                deduped_entries = self._dedupe_jobs(jobs)
                deduped_entries.sort(key=lambda entry: self._entry_sort_key(entry, keyword=keyword))

        refresh_status = self._refresh_liepin_mcp_if_sparse(
            keyword=keyword,
            city=city,
            current_entries=deduped_entries,
            limit=limit,
        )
        if refresh_status is not None:
            source_status["liepin_mcp"] = refresh_status
            if refresh_status.get("status") == "ok" and int(refresh_status.get("records") or 0) > 0:
                jobs = self._load_ranked_jobs(keyword=keyword, city=city)
                deduped_entries = self._dedupe_jobs(jobs)
                deduped_entries.sort(key=lambda entry: self._entry_sort_key(entry, keyword=keyword))

        jobs = [entry["job"] for entry in deduped_entries]
        if not jobs:
            return {"total": 0, "page": 1, "jobs": [], "source_status": source_status}

        if user_id is None:
            visible_entries = deduped_entries[:limit]
            return {
                "total": len(visible_entries),
                "page": 1,
                "jobs": [self._serialize_job(entry["job"], duplicate_context=entry) for entry in visible_entries],
                "source_status": source_status,
            }

        resume = self.resume_repository.get_default_by_user_id(user_id=user_id)
        if resume is None or resume.parsed_content is None:
            if match_resume:
                raise JobServiceError(status_code=400, code=3002, message="Default parsed resume is required")
            visible_entries = deduped_entries[:limit]
            return {
                "total": len(visible_entries),
                "page": 1,
                "jobs": [self._serialize_job(entry["job"], duplicate_context=entry) for entry in visible_entries],
                "source_status": source_status,
            }

        resume_text = self._resume_to_text(resume.parsed_content)
        entry_map = {str(entry["job"].id): entry for entry in deduped_entries}
        scored_jobs = self._score_jobs(jobs=jobs, resume_text=resume_text)
        serialized_jobs = [
            self._serialize_job(
                item["job"],
                match_score=item["score"],
                duplicate_context=entry_map.get(str(item["job"].id)),
            )
            for item in scored_jobs
        ]
        serialized_jobs = recommend_jobs(
            serialized_jobs,
            resume_profile=resume.parsed_content,
            city=city,
        )
        serialized_jobs.sort(
            key=lambda item: (
                0 if item.get("market_region") == "CN" else 1,
                0 if item.get("live_posting") else 1,
                self._source_priority(str(item.get("source") or "")),
                -float(item.get("recommendation_score") or 0),
                -float(item.get("match_score") or 0),
            )
        )
        visible_jobs = serialized_jobs[:limit]
        return {"total": len(visible_jobs), "page": 1, "jobs": visible_jobs, "source_status": source_status}

    def get_job_detail(self, *, job_id: str) -> dict:
        job = self.job_repository.get_by_id(job_id=job_id)
        if job is None or not job.is_active:
            raise JobServiceError(status_code=404, code=3003, message="Job not found")
        return self._serialize_job(job, detail=True)

    def discover_jobs(
        self,
        *,
        user_id: str | None = None,
        match_resume: bool = False,
        keyword: str | None = None,
        city: str | None = None,
        experience: str | None = None,
        skills: tuple[str, ...] = (),
    ) -> dict:
        filters = JobDiscoveryFilters(city=city, experience=experience, skills=skills)
        search_result = RepositoryJobSearcher(self.job_repository).search_jobs(keyword=keyword, filters=filters)
        payload = aggregate_discovered_jobs(
            search_result.candidates,
            filters=filters,
            query_expansions=search_result.query_expansions,
        )

        resume = self.resume_repository.get_default_by_user_id(user_id=user_id) if user_id is not None else None
        if resume is None or resume.parsed_content is None:
            if match_resume:
                raise JobServiceError(status_code=400, code=3002, message="Default parsed resume is required")
            if skills or city or experience:
                payload["jobs"] = recommend_jobs(payload.get("jobs", []), resume_profile={}, city=city, experience=experience, skills=skills)
            return payload

        job_ids = [str(item["id"]) for item in payload.get("jobs", [])]
        scored_jobs = self._score_jobs(jobs=self.job_repository.get_by_ids(job_ids), resume_text=self._resume_to_text(resume.parsed_content))
        score_map = {str(item["job"].id): item["score"] for item in scored_jobs}
        for item in payload.get("jobs", []):
            if str(item["id"]) in score_map:
                item["match_score"] = score_map[str(item["id"])]
        payload["jobs"] = recommend_jobs(
            payload.get("jobs", []),
            resume_profile=resume.parsed_content,
            city=city,
            experience=experience,
            skills=skills,
        )
        payload["jobs"].sort(
            key=lambda item: (
                -float(item.get("recommendation_score") or 0),
                -(item.get("match_score") or 0),
                -int(item.get("popularity_score") or 0),
            )
        )
        return payload

    def _load_ranked_jobs(self, *, keyword: str | None, city: str | None) -> list:
        jobs = []
        seen: set[str] = set()
        for query in _expanded_search_keywords(keyword):
            for job in self.job_repository.list_active_jobs(keyword=query):
                job_id = str(job.id)
                if job_id in seen:
                    continue
                seen.add(job_id)
                jobs.append(job)
        return self._filter_city(jobs, city=city)

    def _refresh_liepin_mcp_if_sparse(self, *, keyword: str | None, city: str | None, current_entries: list[dict], limit: int) -> dict | None:
        keyword_text = (keyword or "").strip()
        intent = _parse_search_intent(keyword_text)
        current_count = len(current_entries)
        has_liepin_result = any(getattr(entry.get("job"), "source", None) == "liepin_mcp" for entry in current_entries)
        # 已有实时岗位时不再为普通查询补抓猎聘，大厂定向查询例外。
        has_live_result = any(self._entry_is_live(entry) for entry in current_entries)
        if current_count > 0 and not has_liepin_result and has_live_result and not _is_big_tech_query(keyword_text):
            return None
        if not keyword_text or current_count >= min(max(limit, 1), 10):
            return None
        if not settings.enable_liepin_mcp or not settings.liepin_mcp_token:
            return None

        query_keyword = intent.role_keyword or keyword_text
        query = f"{query_keyword}@{city.strip()}" if city and city.strip() else query_keyword
        try:
            target_companies = _target_companies_for_refresh(intent=intent, original_text=keyword_text)
            records = []
            if target_companies:
                per_company_limit = min(max(3, limit // max(len(target_companies), 1) + 1), 8)
                for company in target_companies:
                    records.extend(
                        fetch_liepin_mcp_jobs(
                            queries=query,
                            limit_per_query=per_company_limit,
                            company=company,
                        )
                    )
            else:
                records = fetch_liepin_mcp_jobs(
                    queries=query,
                    limit_per_query=min(max(limit, 10), 30),
                    company=intent.company,
                )
            if records:
                sync_real_jobs(fetchers=[lambda: records], deactivate_missing=False)
            return {"status": "ok", "reason": None, "records": len(records)}
        except Exception as exc:
            return {"status": "failed", "reason": str(exc), "records": 0}

    def _refresh_tencent_official_if_company_query(self, *, keyword: str | None, city: str | None, current_entries: list[dict], limit: int) -> dict | None:
        """Refresh Tencent public careers for Tencent + role searches."""
        intent = _parse_search_intent(keyword)
        if not _company_matches("腾讯", intent.company or ""):
            return None
        if len(current_entries) >= min(max(limit, 1), 10):
            return None
        query_keywords = _role_aliases(intent.role_keyword) if intent.role_keyword else ["Java", "后端", "前端", "测试", "产品", "数据", "算法"]
        try:
            records = fetch_tencent_jobs(keywords=query_keywords, page_size=min(max(limit, 10), 30))
            if city:
                city_needle = self._normalize_dedupe_text(city)
                records = [record for record in records if city_needle and city_needle in self._normalize_dedupe_text(record.city or "")]
            if records:
                sync_real_jobs(fetchers=[lambda: records], deactivate_missing=False)
            return {"status": "ok", "reason": None, "records": len(records)}
        except Exception as exc:
            return {"status": "failed", "reason": str(exc), "records": 0}

    def _score_jobs(self, *, jobs: list, resume_text: str) -> list[dict]:
        # 先给每个岗位一个可预测的兜底分，随后再用 Qdrant 相似度覆盖更真实的排序结果。
        scored = self._fallback_scores(jobs=jobs, resume_text=resume_text)
        job_map = {str(job.id): job for job in jobs}

        try:
            qdrant_results = search_similar_jobs(vector=embed_text(resume_text), limit=max(20, len(jobs), 50))
        except Exception:
            qdrant_results = []

        for result in qdrant_results:
            payload = result.payload or {}
            job_id = str(payload.get("job_id", ""))
            if job_id not in scored or job_id not in job_map:
                continue
            scored[job_id] = round(float(result.score) * 100, 2)

        ranked = [
            {"job": job_map[job_id], "score": score}
            for job_id, score in sorted(scored.items(), key=lambda item: item[1], reverse=True)
        ]
        return ranked

    @classmethod
    def _fallback_scores(cls, *, jobs: list, resume_text: str) -> dict[str, float]:
        resume_tokens = cls._tokenize(resume_text)
        scores: dict[str, float] = {}
        for job in jobs:
            job_text = " ".join(filter(None, [job.title, job.company, job.city, job.jd_text or ""]))
            job_tokens = cls._tokenize(job_text)
            overlap = len(resume_tokens & job_tokens)
            coverage = overlap / max(len(job_tokens), 1)
            score = 35.0 + min(55.0, coverage * 100)
            scores[str(job.id)] = round(score, 2)
        return scores

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {token for token in re.findall(r"[a-zA-Z0-9\u4e00-\u9fff]+", text.lower()) if len(token) > 1}

    @staticmethod
    def _resume_to_text(parsed_content: dict) -> str:
        skills = " ".join(parsed_content.get("skills", []))
        projects = " ".join(item.get("name", "") for item in parsed_content.get("projects", []) if isinstance(item, dict))
        summary = parsed_content.get("summary", "")
        return f"summary {summary} skills {skills} projects {projects}".strip()

    @staticmethod
    def _filter_city(jobs: list, *, city: str | None) -> list:
        city_text = (city or "").strip()
        if not city_text:
            return jobs
        needle = JobService._normalize_dedupe_text(city_text)
        return [job for job in jobs if needle and needle in JobService._normalize_dedupe_text(job.city or "")]

    @staticmethod
    def _prefer_china_market(jobs: list) -> list:
        return sorted(
            jobs,
            key=lambda job: (
                0
                if infer_market_region(company=job.company, city=job.city, url=job.apply_url) == "CN"
                else 1,
                job.deadline or date.max,
                str(job.company),
                str(job.title),
            ),
        )

    @staticmethod
    def _dedupe_jobs(jobs: list) -> list[dict]:
        grouped: dict[str, dict] = {}
        for job in jobs:
            entry = JobService._entry_for_job(job)
            keys = JobService._dedupe_keys(job)
            existing_key = next((key for key in keys if key in grouped), None)
            if existing_key is None:
                for key in keys:
                    grouped[key] = entry
                continue

            existing = grouped[existing_key]
            winner = JobService._better_entry(existing, entry)
            merged_sources = sorted(set(existing["merged_sources"]) | set(entry["merged_sources"]))
            winner["merged_sources"] = merged_sources
            winner["duplicate_count"] = max(
                int(existing.get("duplicate_count") or 1) + int(entry.get("duplicate_count") or 1),
                len(merged_sources),
            )

            for key in set(keys + JobService._dedupe_keys(existing["job"])):
                grouped[key] = winner

        unique: dict[str, dict] = {}
        for entry in grouped.values():
            unique[str(entry["job"].id)] = entry
        return list(unique.values())

    @staticmethod
    def _entry_for_job(job) -> dict:
        parsed = job.jd_parsed if isinstance(job.jd_parsed, dict) else {}
        merged_sources = parsed.get("merged_sources") or [job.source]
        duplicate_count = parsed.get("duplicate_count") or len(merged_sources) or 1
        return {"job": job, "merged_sources": list(merged_sources), "duplicate_count": int(duplicate_count)}

    @staticmethod
    def _dedupe_keys(job) -> list[str]:
        keys = [key for key in [JobService._url_key(job.apply_url), JobService._composite_key(job)] if key]
        return keys or [f"id:{job.id}"]

    @staticmethod
    def _url_key(url: str | None) -> str | None:
        if not url:
            return None
        parsed = urlsplit(url)
        significant_query = _significant_url_query(parsed.query)
        cleaned = urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/").lower(), significant_query, ""))
        return f"url:{cleaned}" if cleaned else None

    @staticmethod
    def _composite_key(job) -> str:
        parsed = job.jd_parsed if isinstance(job.jd_parsed, dict) else {}
        job_type = infer_job_type(job.title, job.jd_text, parsed.get("employment_type"))
        taxonomy = classify_title(job.title)
        title = job.title if parsed.get("live_posting") is True else (taxonomy.canonical_title if taxonomy.canonical_confidence >= 0.6 else job.title)
        return "|".join(
            [
                JobService._normalize_dedupe_text(job.company or ""),
                JobService._normalize_dedupe_text(title),
                JobService._normalize_dedupe_text(job.city or ""),
                job_type,
            ]
        )

    @staticmethod
    def _better_entry(left: dict, right: dict) -> dict:
        return left if JobService._quality_key(left["job"]) <= JobService._quality_key(right["job"]) else right

    @staticmethod
    def _quality_key(job) -> tuple:
        parsed = job.jd_parsed if isinstance(job.jd_parsed, dict) else {}
        posted_at = str(parsed.get("posted_at") or "")
        return (
            JobService._live_rank(job),
            JobService._source_priority(job.source),
            0 if infer_market_region(company=job.company, city=job.city, url=job.apply_url) == "CN" else 1,
            -(len(job.jd_text or "")),
            -len(posted_at),
            str(job.external_id or ""),
        )

    @staticmethod
    def _entry_sort_key(entry: dict, *, keyword: str | None = None) -> tuple:
        job = entry["job"]
        parsed = job.jd_parsed if isinstance(job.jd_parsed, dict) else {}
        posted_at = str(parsed.get("posted_at") or "")
        return (
            JobService._query_relevance_rank(job, keyword=keyword),
            0 if infer_market_region(company=job.company, city=job.city, url=job.apply_url) == "CN" else 1,
            JobService._live_rank(job),
            JobService._source_priority(job.source),
            0 if job.is_active else 1,
            job.deadline or date.max,
            -len(posted_at),
            str(job.company),
            str(job.title),
        )

    @staticmethod
    def _query_relevance_rank(job, *, keyword: str | None) -> int:
        intent = _parse_search_intent(keyword)
        title = (job.title or "").lower()
        jd_text = (job.jd_text or "").lower()
        company = job.company or ""
        if intent.company and not _company_matches(intent.company, company):
            return 50

        aliases = [alias.lower() for alias in _role_aliases(intent.role_keyword)]
        primary = aliases[0] if aliases else intent.role_keyword.lower()
        if primary and primary in title:
            return 0
        if any(alias and alias in title for alias in aliases):
            return 1
        if primary and primary in jd_text:
            return 2
        if any(alias and alias in jd_text for alias in aliases):
            return 3
        return 5 if not intent.role_keyword else 8

    @staticmethod
    def _source_priority(source: str) -> int:
        priority = {
            "official_company": 0,
            "liepin_mcp": 1,
            "public_board": 1,
            "third_party_search": 2,
            "seed": 3,
            "manual": 3,
            "ashby": 4,
            "greenhouse": 4,
            "lever": 4,
            "market_baseline": 5,
            "mock": 9,
        }
        return priority.get(source, 8)

    @staticmethod
    def _live_rank(job) -> int:
        """Prefer current postings over static career-entry coverage records."""
        parsed = job.jd_parsed if isinstance(job.jd_parsed, dict) else {}
        return 0 if parsed.get("live_posting") is True else 1

    @staticmethod
    def _entry_is_live(entry: dict) -> bool:
        """Return whether a deduped search entry points to a live posting."""
        job = entry.get("job") if isinstance(entry, dict) else None
        if job is None:
            return False
        parsed = job.jd_parsed if isinstance(job.jd_parsed, dict) else {}
        return parsed.get("live_posting") is True

    @staticmethod
    def _normalize_dedupe_text(value: str) -> str:
        return "".join(ch for ch in value.lower() if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")

    @staticmethod
    def _serialize_job(job, match_score: float | None = None, detail: bool = False, duplicate_context: dict | None = None) -> dict:
        taxonomy = classify_title(job.title)
        skills = extract_skills(" ".join([job.title, job.jd_text or ""]))
        parsed = job.jd_parsed if isinstance(job.jd_parsed, dict) else {}
        job_type = infer_job_type(job.title, job.jd_text, parsed.get("employment_type"))
        market_region = infer_market_region(company=job.company, city=job.city, url=job.apply_url)
        merged_sources = (
            duplicate_context.get("merged_sources")
            if duplicate_context
            else parsed.get("merged_sources", [job.source])
        )
        duplicate_count = duplicate_context.get("duplicate_count") if duplicate_context else parsed.get("duplicate_count", len(merged_sources))
        payload = {
            "id": str(job.id),
            "job_id": str(job.id),
            "title": job.title,
            "raw_title": job.title,
            "canonical_title": taxonomy.canonical_title,
            "function": taxonomy.function,
            "specialization": taxonomy.specialization,
            "canonical_confidence": taxonomy.canonical_confidence,
            "company": job.company,
            "city": job.city,
            "salary": job.salary_range,
            "duration": job.duration,
            "deadline": job.deadline.isoformat() if job.deadline else None,
            "posted_at": parsed.get("posted_at"),
            "source": job.source,
            "apply_url": job.apply_url or "",
            "jd_text": job.jd_text,
            "summary": job.jd_text[:320] if job.jd_text else None,
            "skills": skills,
            "experience": infer_experience(job.title, job.jd_text),
            "job_type": job_type,
            "job_type_label": job_type_label(job_type),
            "market_region": market_region,
            "last_seen_at": job.crawled_at.isoformat() if job.crawled_at else None,
            "is_active": job.is_active,
            "live_posting": bool(parsed.get("live_posting")),
            "merged_sources": merged_sources,
            "duplicate_count": duplicate_count,
        }
        if detail:
            payload["interview_context"] = {
                "company": job.company,
                "title": job.title,
                "city": job.city,
                "salary": job.salary_range,
                "job_type": job_type,
                "job_type_label": job_type_label(job_type),
                "skills": skills,
                "jd_summary": job.jd_text[:1200] if job.jd_text else "",
            }
        if match_score is not None:
            payload["match_score"] = match_score
        return payload


_KNOWN_COMPANY_ALIASES: tuple[tuple[str, str], ...] = (
    ("腾讯", "腾讯"),
    ("tencent", "腾讯"),
    ("阿里巴巴", "阿里巴巴"),
    ("阿里云", "阿里巴巴"),
    ("阿里", "阿里巴巴"),
    ("alibaba", "阿里巴巴"),
    ("字节跳动", "字节跳动"),
    ("字节", "字节跳动"),
    ("bytedance", "字节跳动"),
    ("百度", "百度"),
    ("baidu", "百度"),
    ("京东", "京东"),
    ("jd", "京东"),
    ("美团", "美团"),
    ("meituan", "美团"),
    ("快手", "快手"),
    ("kuaishou", "快手"),
    ("小米", "小米"),
    ("xiaomi", "小米"),
    ("华为", "华为"),
    ("huawei", "华为"),
    ("网易", "网易"),
    ("netease", "网易"),
    ("哔哩哔哩", "哔哩哔哩"),
    ("bilibili", "哔哩哔哩"),
    ("小红书", "小红书"),
    ("xiaohongshu", "小红书"),
)

_BIG_TECH_MARKERS = ("大厂", "互联网大厂", "头部互联网", "互联网")
_BIG_TECH_REFRESH_COMPANIES = ("腾讯", "阿里巴巴", "字节跳动", "百度", "美团")
_COMPANY_QUERY_NAMES: dict[str, tuple[str, ...]] = {
    "腾讯": ("腾讯", "Tencent"),
    "阿里巴巴": ("阿里巴巴", "阿里", "阿里云", "Alibaba"),
    "字节跳动": ("字节跳动", "字节", "ByteDance"),
    "百度": ("百度", "Baidu"),
    "京东": ("京东", "JD"),
    "美团": ("美团", "Meituan"),
    "快手": ("快手", "Kuaishou"),
    "小米": ("小米", "Xiaomi"),
    "华为": ("华为", "Huawei"),
    "网易": ("网易", "NetEase"),
    "哔哩哔哩": ("哔哩哔哩", "B站", "bilibili"),
    "小红书": ("小红书", "Xiaohongshu"),
}
_ROLE_ALIAS_GROUPS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("java",), ("Java", "后端", "后台", "服务端", "服务端研发", "开发")),
    (("后端", "backend", "后台", "服务端"), ("后端", "后台", "服务端", "服务端研发", "Java", "Golang", "开发")),
    (("前端", "frontend", "web"), ("前端", "Web前端", "客户端", "开发")),
    (("算法", "机器学习", "推荐", "搜索", "ai", "大模型"), ("算法", "机器学习", "推荐", "搜索", "AI", "大模型", "LLM")),
    (("产品", "pm", "product"), ("产品", "产品经理", "AI产品", "数据产品", "策略产品", "增长产品")),
    (("数据", "data", "分析", "bi"), ("数据", "数据分析", "数据开发", "BI", "数仓", "数据产品")),
    (("测试", "qa", "质量"), ("测试", "测试开发", "质量", "QA")),
    (("运营", "operation"), ("运营", "用户运营", "产品运营", "内容运营", "策略运营")),
    (("市场", "marketing"), ("市场", "品牌", "增长", "营销")),
)


def _parse_search_intent(keyword: str | None) -> JobSearchIntent:
    """Extract company and role tokens from mixed search text such as Tencent + Java."""
    text = (keyword or "").strip()
    if not text:
        return JobSearchIntent(company=None, role_keyword="")
    lowered = text.lower()
    for alias, company in _KNOWN_COMPANY_ALIASES:
        alias_lower = alias.lower()
        if alias_lower not in lowered:
            continue
        flags = re.IGNORECASE if alias.isascii() else 0
        role = re.sub(re.escape(alias), " ", text, flags=flags)
        role = _clean_search_role(role)
        return JobSearchIntent(company=company, role_keyword=role)
    return JobSearchIntent(company=None, role_keyword=_clean_search_role(text))


def _clean_search_role(text: str) -> str:
    role = text
    for marker in _BIG_TECH_MARKERS:
        role = role.replace(marker, " ")
    role = re.sub(r"[\s,，、|+_-]+", " ", role).strip()
    return role


def _expanded_search_keywords(keyword: str | None) -> list[str | None]:
    """Expand Chinese market role wording while keeping company constraints."""
    text = (keyword or "").strip()
    if not text:
        return [None]

    intent = _parse_search_intent(text)
    aliases = _role_aliases(intent.role_keyword)
    queries: list[str | None] = [] if _is_big_tech_query(text) and not intent.company else [text]

    if intent.company:
        for company_name in _company_query_names(intent.company):
            if intent.role_keyword:
                queries.append(f"{company_name} {intent.role_keyword}")
            for alias in aliases:
                queries.append(f"{company_name} {alias}")
    elif _is_big_tech_query(text):
        for company in _BIG_TECH_REFRESH_COMPANIES:
            for company_name in _company_query_names(company)[:2]:
                for alias in aliases or [intent.role_keyword]:
                    if alias:
                        queries.append(f"{company_name} {alias}")
    else:
        for alias in aliases:
            queries.append(alias)

    unique: list[str | None] = []
    seen: set[str] = set()
    for item in queries:
        key = item or ""
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _role_aliases(role_keyword: str | None) -> list[str]:
    role = (role_keyword or "").strip()
    if not role:
        return []
    lowered = role.lower()
    for triggers, aliases in _ROLE_ALIAS_GROUPS:
        if any(trigger in lowered for trigger in triggers):
            result = [role, *aliases]
            return _unique_texts(result)
    return [role]


def _company_query_names(company: str | None) -> tuple[str, ...]:
    if not company:
        return ()
    return _COMPANY_QUERY_NAMES.get(company, (company,))


def _company_matches(expected: str, actual: str) -> bool:
    if not expected or not actual:
        return False
    expected_names = _company_query_names(expected) or (expected,)
    actual_normalized = JobService._normalize_dedupe_text(actual)
    return any(JobService._normalize_dedupe_text(name) in actual_normalized for name in expected_names)


def _is_big_tech_query(text: str | None) -> bool:
    lowered = (text or "").lower()
    return any(marker.lower() in lowered for marker in _BIG_TECH_MARKERS)


def _target_companies_for_refresh(*, intent: JobSearchIntent, original_text: str) -> tuple[str, ...]:
    if intent.company:
        return (intent.company,)
    if _is_big_tech_query(original_text):
        return _BIG_TECH_REFRESH_COMPANIES
    return ()


def _unique_texts(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = item.strip()
        key = value.lower()
        if not value or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _significant_url_query(query: str) -> str:
    """Keep job identity query params while stripping tracking noise."""
    identity_keys = {"id", "jobid", "postid", "positionid", "recruitpostid"}
    pairs = [(key, value) for key, value in parse_qsl(query, keep_blank_values=False) if key.lower() in identity_keys]
    return urlencode(sorted(pairs))
