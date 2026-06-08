from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import session_local
from app.main import app
from app.models.job import Job
from app.repositories.resume_repository import ResumeRepository
from app.tools.job_discovery import (
    JobDiscoveryFilters,
    JobSearchCandidate,
    aggregate_discovered_jobs,
    canonicalize_title,
    classify_title,
    expand_job_queries,
    infer_experience,
    recommend_jobs,
)

client = TestClient(app)


def _reset_jobs() -> None:
    with session_local() as session:
        session.execute(text("DELETE FROM chat_sessions"))
        session.execute(text("DELETE FROM interview_sessions"))
        session.execute(text("DELETE FROM applications"))
        session.execute(text("DELETE FROM resumes"))
        session.execute(text("DELETE FROM jobs"))
        session.execute(text("DELETE FROM users"))
        session.commit()


def test_query_expansion_keeps_chinese_and_english_product_terms() -> None:
    expanded = expand_job_queries("产品")

    assert "产品" in expanded
    assert "Product" in expanded
    assert "Product Manager" in expanded
    assert "Associate Product Manager" in expanded


def test_infer_experience_uses_word_boundaries_for_intern() -> None:
    assert infer_experience("Product Manager Intern", "Own product features") == "intern"
    assert infer_experience("Product Manager, New Grad", "Build tools for internal data users") == "entry"
    assert infer_experience("Sr. Product Manager - Technical", "Own product strategy") == "senior"


def test_canonicalize_title_keeps_formal_roles_separate_from_internships() -> None:
    assert canonicalize_title("Product Manager | Growth") == "产品经理"
    assert canonicalize_title("Associate Product Manager Intern") == "产品经理实习生"
    assert infer_experience("Product Manager | Growth", "Lead activation experiments") == "unspecified"


def test_aggregate_discovered_jobs_standardizes_dedupes_and_scores_popularity() -> None:
    candidates = [
        JobSearchCandidate(
            id="1",
            raw_title="Associate Product Manager Intern",
            company="Notion",
            city="Shanghai",
            source="ashby",
            url="https://jobs.ashbyhq.com/notion/1",
            summary="Own product roadmap, user research, SQL analysis.",
            salary=None,
            duration=None,
            deadline=None,
        ),
        JobSearchCandidate(
            id="1-duplicate",
            raw_title="Associate Product Manager Intern",
            company="Notion",
            city="Shanghai",
            source="ashby",
            url="https://jobs.ashbyhq.com/notion/1",
            summary="Duplicate copy should not create another posting.",
            salary=None,
            duration=None,
            deadline=None,
        ),
        JobSearchCandidate(
            id="2",
            raw_title="产品经理实习生",
            company="字节跳动",
            city="北京",
            source="seed",
            url="https://jobs.bytedance.com/zh/position/2",
            summary="产品需求分析、用户研究、SQL 数据分析。",
            salary=None,
            duration=None,
            deadline=None,
        ),
        JobSearchCandidate(
            id="3",
            raw_title="Backend Engineer Intern",
            company="Databricks",
            city="Remote",
            source="greenhouse",
            url="https://boards.greenhouse.io/databricks/jobs/3",
            summary="Python backend service development.",
            salary=None,
            duration=None,
            deadline=None,
        ),
    ]

    result = aggregate_discovered_jobs(candidates, filters=JobDiscoveryFilters(skills=("SQL",)))

    assert result["total"] == 2
    assert result["jobs"][0]["market_region"] == "CN"
    notion_job = next(job for job in result["jobs"] if job["company"] == "Notion")
    assert notion_job["raw_title"] == "Associate Product Manager Intern"
    assert notion_job["canonical_title"] == "产品经理实习生"
    assert notion_job["experience"] == "intern"
    assert "SQL" in notion_job["skills"]
    assert notion_job["popularity_score"] >= 70
    assert notion_job["source_frequency"] == 2
    assert notion_job["url"] == "https://jobs.ashbyhq.com/notion/1"


def test_jobs_discover_uses_external_synced_jobs_and_structured_schema() -> None:
    _reset_jobs()
    with session_local() as session:
        session.add_all(
            [
                Job(
                    external_id="ashby-product-1",
                    source="ashby",
                    title="Associate Product Manager Intern",
                    company="Notion",
                    city="Shanghai",
                    salary_range="$40/hour",
                    duration="12 weeks",
                    jd_text="Own product features, SQL analysis, user research and roadmap execution.",
                    apply_url="https://jobs.ashbyhq.com/notion/1",
                    deadline=date(2026, 5, 20),
                    is_active=True,
                ),
                Job(
                    external_id="greenhouse-product-2",
                    source="greenhouse",
                    title="Product Operations Intern",
                    company="Airbnb",
                    city="San Francisco",
                    salary_range="$35/hour",
                    duration="3 months",
                    jd_text="Product operations, marketplace analysis, SQL, experimentation and stakeholder communication.",
                    apply_url="https://boards.greenhouse.io/airbnb/jobs/2",
                    deadline=date(2026, 5, 22),
                    is_active=True,
                ),
                Job(
                    external_id="seed-product-3",
                    source="seed",
                    title="增长产品实习生",
                    company="小红书",
                    city="上海",
                    salary_range="220-280元/天",
                    duration="6个月",
                    jd_text="增长实验、用户研究、SQL、A/B 测试和数据分析。",
                    apply_url="https://job.xiaohongshu.com/campus/3",
                    deadline=date(2026, 5, 24),
                    is_active=True,
                ),
                Job(
                    external_id="greenhouse-infra-noise",
                    source="greenhouse",
                    title="Senior Software Engineer, Data Infrastructure",
                    company="Airbnb",
                    city="USA - Remote",
                    salary_range="$80/hour",
                    duration=None,
                    jd_text="Build infrastructure for a product company. SQL and data warehouse experience required.",
                    apply_url="https://boards.greenhouse.io/airbnb/jobs/noise",
                    deadline=date(2026, 5, 25),
                    is_active=True,
                ),
            ]
        )
        session.commit()

    response = client.get("/api/v1/jobs/discover?keyword=产品&skills=SQL")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["source_kind"] == "external_synced"
    assert data["fallback_notice"] is None
    assert "Product" in data["query_expansions"]
    assert data["total"] >= 3

    first = data["jobs"][0]
    expected_fields = {
        "raw_title",
        "canonical_title",
        "city",
        "experience",
        "skills",
        "company",
        "source",
        "url",
        "summary",
        "popularity_score",
    }
    assert expected_fields <= set(first)
    assert first["canonical_title"]
    assert first["raw_title"] != "产品"
    assert first["url"].startswith("https://")
    assert all("Software Engineer" not in item["raw_title"] for item in data["jobs"])


def test_jobs_discover_marks_local_seed_results_when_no_external_source_exists() -> None:
    _reset_jobs()
    with session_local() as session:
        session.add(
            Job(
                external_id="seed-product-only",
                source="seed",
                title="产品经理实习生",
                company="字节跳动",
                city="北京",
                salary_range="220-300元/天",
                duration="6个月",
                jd_text="产品需求分析、SQL 和用户研究。",
                apply_url="https://jobs.bytedance.com/zh/position/seed-product-only",
                deadline=date(2026, 5, 20),
                is_active=True,
            )
        )
        session.commit()

    response = client.get("/api/v1/jobs/discover?keyword=产品")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["source_kind"] == "local_seed"
    assert "不是实时市场全集" in data["fallback_notice"]


def test_taxonomy_classifies_function_specialization_and_confidence() -> None:
    ai_pm = classify_title("AI Product Manager Intern - LLM Platform")
    assert ai_pm.function == "Product"
    assert ai_pm.canonical_title == "AI Product Manager Intern"
    assert ai_pm.specialization == "LLM"
    assert ai_pm.canonical_confidence >= 0.85

    java_backend = classify_title("Java后端开发工程师")
    assert java_backend.function == "Engineering"
    assert java_backend.canonical_title == "Java Backend Engineer"
    assert java_backend.specialization == "Java"
    assert java_backend.canonical_confidence >= 0.8

    unknown = classify_title("Campus Builder Program")
    assert unknown.function == "Other"
    assert unknown.canonical_confidence < 0.55


def test_query_expansion_handles_cn_en_ai_product_manager_terms() -> None:
    expanded_cn = expand_job_queries("AI 产品经理")
    expanded_en = expand_job_queries("AI PM")

    assert "AI 产品经理" in expanded_cn
    assert "AI Product Manager" in expanded_cn
    assert "AI PM" in expanded_en
    assert "Product Manager" in expanded_en


def test_dedupe_taxonomy_popularity_recency_and_rag_payload_are_stable() -> None:
    now = datetime.utcnow()
    candidates = [
        JobSearchCandidate(
            id="ashby-1",
            raw_title="Java后端开发工程师",
            company="Acme",
            city="上海",
            source="ashby",
            url="https://jobs.ashbyhq.com/acme/123-java-backend",
            summary="Java Redis SQL backend platform.",
            salary=None,
            duration=None,
            deadline=None,
            employment_type="full_time",
            posted_at=now - timedelta(days=3),
            last_seen_at=now,
            is_active=True,
        ),
        JobSearchCandidate(
            id="greenhouse-dup",
            raw_title="后端研发工程师（Java）",
            company="ACME Inc.",
            city="上海",
            source="greenhouse",
            url="https://boards.greenhouse.io/acme/jobs/123-java-backend",
            summary="Java Redis SQL backend platform duplicate.",
            salary=None,
            duration=None,
            deadline=None,
            employment_type="full_time",
            posted_at=now - timedelta(days=2),
            last_seen_at=now,
            is_active=True,
        ),
        JobSearchCandidate(
            id="old-2",
            raw_title="Golang Backend Engineer",
            company="DataCo",
            city="北京",
            source="ashby",
            url="https://jobs.ashbyhq.com/dataco/go-backend",
            summary="Go Redis distributed systems.",
            salary=None,
            duration=None,
            deadline=None,
            employment_type="full_time",
            posted_at=now - timedelta(days=180),
            last_seen_at=now - timedelta(days=120),
            is_active=True,
        ),
    ]

    result = aggregate_discovered_jobs(candidates, filters=JobDiscoveryFilters(skills=("Redis",)))

    assert result["total"] == 2
    first = result["jobs"][0]
    assert first["function"] == "Engineering"
    assert first["canonical_title"] == "Java Backend Engineer"
    assert first["specialization"] == "Java"
    assert first["canonical_confidence"] >= 0.8
    assert first["source_frequency"] == 2
    assert first["posted_at"] is not None
    assert first["last_seen_at"] is not None
    assert first["is_active"] is True
    assert first["popularity_score"] > result["jobs"][1]["popularity_score"]
    metadata = first["rag_payload"]["metadata"]
    assert metadata["function"] == "Engineering"
    assert metadata["canonical_title"] == "Java Backend Engineer"
    assert metadata["specialization"] == "Java"
    assert metadata["popularity_score"] == first["popularity_score"]
    assert first["rag_payload"]["document_id"].startswith("job:")


def test_recommend_jobs_returns_explanations_gaps_and_priority() -> None:
    result = aggregate_discovered_jobs(
        [
            JobSearchCandidate(
                id="pm-1",
                raw_title="AI Product Manager Intern",
                company="Cursor",
                city="上海",
                source="ashby",
                url="https://jobs.ashbyhq.com/cursor/ai-pm",
                summary="LLM product roadmap, SQL analysis, user research and Python prototype.",
                salary=None,
                duration=None,
                deadline=None,
                employment_type="intern",
                posted_at=datetime.utcnow() - timedelta(days=2),
                last_seen_at=datetime.utcnow(),
                is_active=True,
            ),
            JobSearchCandidate(
                id="backend-1",
                raw_title="Backend Engineer Intern",
                company="Databricks",
                city="北京",
                source="greenhouse",
                url="https://boards.greenhouse.io/databricks/jobs/backend",
                summary="Backend services, Redis, Kubernetes and Go.",
                salary=None,
                duration=None,
                deadline=None,
                employment_type="intern",
                posted_at=datetime.utcnow() - timedelta(days=5),
                last_seen_at=datetime.utcnow(),
                is_active=True,
            ),
        ],
        filters=JobDiscoveryFilters(city="上海", experience="intern", skills=("SQL",)),
    )

    recommended = recommend_jobs(
        result["jobs"],
        resume_profile={"skills": ["SQL", "Python", "User Research"], "summary": "AI product intern with data analysis projects"},
        city="上海",
        experience="intern",
        skills=("SQL",),
    )

    first = recommended[0]
    assert first["raw_title"] == "AI Product Manager Intern"
    assert first["recommendation_score"] >= first["skill_match_score"]
    assert first["city_match_score"] == 1.0
    assert first["application_priority"] in {"high", "medium"}
    assert "SQL" in first["matched_skills"]
    assert "explanation" in first
    assert isinstance(first["missing_skills"], list)
    assert isinstance(first["suggested_resume_improvements"], list)


def test_jobs_search_adds_recommendation_explanation_for_authenticated_user() -> None:
    _reset_jobs()
    register_resp = client.post(
        "/api/v1/auth/register",
        json={"email": "recommend-search@example.com", "password": "Test1234!", "name": "Recommend User"},
    )
    user_id = register_resp.json()["data"]["user_id"]
    headers = {"Authorization": f"Bearer {register_resp.json()['data']['access_token']}"}

    with session_local() as session:
        session.add(
            Job(
                external_id="official-ai-pm-1",
                source="official_company",
                title="AI Product Manager Intern",
                company="ByteDance",
                city="Beijing",
                salary_range="250-350/day",
                duration="6 months",
                jd_text="Own LLM product requirements, SQL analysis, user research and stakeholder communication.",
                apply_url="https://jobs.bytedance.com/zh/position/ai-pm-1",
                deadline=date(2026, 5, 20),
                is_active=True,
            )
        )
        session.commit()
        resume_repo = ResumeRepository(session)
        resume = resume_repo.create(
            user_id=user_id,
            file_url="/tmp/recommend-search.docx",
            file_name="recommend-search.docx",
            parse_status="done",
        )
        resume_repo.mark_done(
            resume=resume,
            parsed_content={
                "summary": "AI product intern candidate with SQL, user research and Python projects.",
                "skills": ["SQL", "User Research", "Python"],
                "projects": [{"name": "AIGC product analysis"}],
            },
            score_report={"overall_score": 86, "status": "ready"},
        )

    response = client.get("/api/v1/jobs/search?keyword=Product&city=Beijing&limit=5", headers=headers)

    assert response.status_code == 200
    job = response.json()["data"]["jobs"][0]
    assert job["match_score"] >= 0
    assert job["recommendation_score"] > 0
    assert "SQL" in job["matched_skills"]
    assert isinstance(job["missing_skills"], list)
    assert job["application_priority"] in {"high", "medium", "low"}
    assert job["explanation"]
