from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import session_local
from app.main import app
from app.models.job import Job
from app.repositories.resume_repository import ResumeRepository
from app.scripts.sync_real_jobs import sync_real_jobs
from app.tools.job_sources import JobSourceRecord
from app.tools.job_sources import fetch_market_baseline_jobs, fetch_official_company_jobs

client = TestClient(app)


def _reset_search_data() -> None:
    with session_local() as session:
        session.execute(text("DELETE FROM chat_sessions"))
        session.execute(text("DELETE FROM interview_sessions"))
        session.execute(text("DELETE FROM applications"))
        session.execute(text("DELETE FROM resumes"))
        session.execute(text("DELETE FROM jobs"))
        session.execute(text("DELETE FROM users"))
        session.commit()


def _create_user_and_resume_and_jobs() -> str:
    _reset_search_data()
    register_resp = client.post(
        "/api/v1/auth/register",
        json={"email": "search@example.com", "password": "Test1234!", "name": "搜索用户"},
    )
    access_token = register_resp.json()["data"]["access_token"]
    user_id = register_resp.json()["data"]["user_id"]

    with session_local() as session:
        resume_repo = ResumeRepository(session)
        resume = resume_repo.create(
            user_id=user_id,
            file_url="/tmp/resume.pdf",
            file_name="resume.pdf",
            parse_status="done",
        )
        resume.parsed_content = {
            "skills": ["Python", "SQL", "FastAPI"],
            "projects": [{"name": "InternAgent"}],
        }
        resume.is_default = True
        session.add(resume)
        session.add_all(
            [
                Job(
                    external_id="job-match-1",
                    source="manual",
                    title="Backend Intern",
                    company="Alpha",
                    city="Shanghai",
                    salary_range="200/day",
                    duration="3 months",
                    jd_text="Python SQL FastAPI Redis",
                    apply_url="https://careers.tencent.com/job-alpha",
                    deadline=date(2026, 4, 30),
                    is_active=True,
                ),
                Job(
                    external_id="job-match-2",
                    source="manual",
                    title="Operations Intern",
                    company="Beta",
                    city="Beijing",
                    salary_range="150/day",
                    duration="3 months",
                    jd_text="Excel communication docs",
                    apply_url="https://careers.bytedance.com/job-beta",
                    deadline=date(2026, 5, 10),
                    is_active=True,
                ),
            ]
        )
        session.commit()

    return access_token


def test_jobs_search_returns_match_score_when_match_resume_enabled() -> None:
    access_token = _create_user_and_resume_and_jobs()

    client.post("/api/v1/auth/login", json={"email": "search@example.com", "password": "Test1234!"})
    with session_local() as session:
        from app.scripts.reindex_embeddings import rebuild_job_embeddings, rebuild_resume_embeddings

        rebuild_job_embeddings(session)
        rebuild_resume_embeddings(session)

    response = client.get(
        "/api/v1/jobs/search?match_resume=true",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["total"] >= 1
    assert "match_score" in body["data"]["jobs"][0]


def test_jobs_search_without_match_resume_works_anonymously() -> None:
    _create_user_and_resume_and_jobs()

    response = client.get("/api/v1/jobs/search")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["total"] >= 2
    assert "match_score" not in body["data"]["jobs"][0]


def test_sync_real_jobs_populates_domestic_catalog_without_seed_script() -> None:
    _reset_search_data()

    result = sync_real_jobs(fetchers=[lambda: fetch_official_company_jobs() + fetch_market_baseline_jobs()])

    with session_local() as session:
        rows = session.execute(
            text(
                """
                select title, company, city, salary_range, jd_text
                from jobs
                where source in ('official_company', 'market_baseline')
                order by external_id
                """
            )
        ).mappings().all()

    assert result["synced_jobs"] >= 20
    assert len(rows) >= 20
    assert all(row["title"] and row["company"] and row["city"] and row["salary_range"] and row["jd_text"] for row in rows)
    product_rows = [row for row in rows if "产品" in row["title"] or "产品" in row["jd_text"]]
    assert len(product_rows) >= 6

    with session_local() as session:
        example_links = session.execute(text("select count(*) from jobs where apply_url like '%example.com%'")).scalar_one()
    assert example_links == 0


def test_jobs_search_keyword_returns_match_score_for_authenticated_resume() -> None:
    access_token = _create_user_and_resume_and_jobs()

    with session_local() as session:
        session.add_all(
            [
                Job(
                    external_id="job-product-1",
                    source="manual",
                    title="产品经理实习生",
                    company="Gamma",
                    city="Shanghai",
                    salary_range="220/day",
                    duration="4 months",
                    jd_text="产品分析 用户研究 SQL 数据分析",
                    apply_url="https://jobs.bytedance.com/zh/position/gamma",
                    deadline=date(2026, 4, 28),
                    is_active=True,
                ),
                Job(
                    external_id="job-product-2",
                    source="manual",
                    title="产品运营实习生",
                    company="Delta",
                    city="Beijing",
                    salary_range="180/day",
                    duration="3 months",
                    jd_text="产品增长 A/B测试 SQL 沟通协作",
                    apply_url="https://zhaopin.meituan.com/web/position/delta",
                    deadline=date(2026, 5, 3),
                    is_active=True,
                ),
            ]
        )
        session.commit()

        from app.scripts.reindex_embeddings import rebuild_job_embeddings, rebuild_resume_embeddings

        rebuild_job_embeddings(session)
        rebuild_resume_embeddings(session)

    response = client.get(
        "/api/v1/jobs/search?keyword=产品",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["total"] >= 2
    assert all("产品" in job["title"] for job in body["data"]["jobs"])
    assert all("match_score" in job for job in body["data"]["jobs"])


def test_jobs_search_never_returns_example_apply_urls(monkeypatch) -> None:
    import app.services.job_service as job_service_module

    _reset_search_data()
    monkeypatch.setattr(job_service_module.settings, "enable_liepin_mcp", False)
    with session_local() as session:
        session.add_all(
            [
                Job(
                    external_id="job-fake-url",
                    source="manual",
                    title="产品实习生",
                    company="Fake",
                    city="Shanghai",
                    salary_range="200/day",
                    duration="3 months",
                    jd_text="产品 SQL",
                    apply_url="https://example.com/fake",
                    deadline=date(2026, 5, 1),
                    is_active=True,
                ),
                Job(
                    external_id="job-real-url",
                    source="manual",
                    title="产品实习生",
                    company="Real",
                    city="Shanghai",
                    salary_range="200/day",
                    duration="3 months",
                    jd_text="产品 SQL",
                    apply_url="https://jobs.bytedance.com/zh/position/real",
                    deadline=date(2026, 5, 1),
                    is_active=True,
                ),
            ]
        )
        session.commit()

    response = client.get("/api/v1/jobs/search?keyword=产品")

    assert response.status_code == 200
    jobs = response.json()["data"]["jobs"]
    assert len(jobs) == 1
    assert "example.com" not in jobs[0]["apply_url"]


def test_jobs_search_prefers_china_market_and_exposes_display_fields(monkeypatch) -> None:
    import app.services.job_service as job_service_module

    _reset_search_data()
    monkeypatch.setattr(job_service_module.settings, "enable_liepin_mcp", False)
    with session_local() as session:
        session.add_all(
            [
                Job(
                    external_id="global-product",
                    source="greenhouse",
                    title="Product Manager",
                    company="Airbnb",
                    city="San Francisco",
                    salary_range="$40/hour",
                    duration=None,
                    jd_text="Product roadmap, SQL and marketplace experiments.",
                    apply_url="https://boards.greenhouse.io/airbnb/jobs/global-product",
                    deadline=date(2026, 5, 1),
                    is_active=True,
                ),
                Job(
                    external_id="cn-product",
                    source="seed",
                    title="产品经理实习生",
                    company="字节跳动",
                    city="北京",
                    salary_range="220-300元/天",
                    duration="6个月",
                    jd_text="负责产品需求分析、用户研究、SQL 数据分析和增长实验。",
                    apply_url="https://jobs.bytedance.com/zh/position/cn-product",
                    deadline=date(2026, 5, 2),
                    is_active=True,
                ),
            ]
        )
        session.commit()

    response = client.get("/api/v1/jobs/search?keyword=产品")

    assert response.status_code == 200
    jobs = response.json()["data"]["jobs"]
    assert jobs[0]["company"] == "字节跳动"
    assert jobs[0]["market_region"] == "CN"
    assert jobs[0]["job_type"] == "intern"
    assert jobs[0]["job_type_label"] == "实习"
    assert jobs[0]["salary"] == "220-300元/天"
    assert jobs[0]["city"] == "北京"


def test_jobs_search_prefers_liepin_mcp_over_market_baseline() -> None:
    _reset_search_data()
    with session_local() as session:
        session.add_all(
            [
                Job(
                    external_id="baseline-product",
                    source="market_baseline",
                    title="产品经理",
                    company="互联网主流岗位",
                    city="北京",
                    salary_range="面议",
                    duration=None,
                    jd_text="产品经理主流职业覆盖，不代表实时招聘岗位。",
                    apply_url="https://jobs.bytedance.com/zh/position?keywords=product",
                    deadline=date(2026, 5, 1),
                    is_active=True,
                ),
                Job(
                    external_id="liepin-real-product",
                    source="liepin_mcp",
                    title="产品经理",
                    company="猎聘真实公司",
                    city="北京-朝阳区",
                    salary_range="20-35k",
                    duration=None,
                    jd_text="负责产品规划、SQL 分析和用户研究。",
                    apply_url="https://www.liepin.com/job/1976552101.shtml",
                    deadline=date(2026, 5, 2),
                    is_active=True,
                ),
            ]
        )
        session.commit()

    response = client.get("/api/v1/jobs/search?keyword=产品经理&city=北京&limit=2")

    assert response.status_code == 200
    jobs = response.json()["data"]["jobs"]
    assert jobs[0]["source"] == "liepin_mcp"
    assert jobs[0]["company"] == "猎聘真实公司"


def test_jobs_search_prefers_live_liepin_mcp_over_static_official_catalog() -> None:
    _reset_search_data()
    with session_local() as session:
        session.add_all(
            [
                Job(
                    external_id="official-static-product",
                    source="official_company",
                    title="产品经理",
                    company="静态官网目录",
                    city="北京",
                    salary_range="面议",
                    duration=None,
                    jd_text="企业招聘入口目录，非实时岗位详情。",
                    apply_url="https://careers.example.cn/product",
                    is_active=True,
                    jd_parsed={"live_posting": False, "market_region": "CN"},
                ),
                Job(
                    external_id="liepin-live-product",
                    source="liepin_mcp",
                    title="产品经理",
                    company="猎聘实时公司",
                    city="北京",
                    salary_range="20-35k",
                    duration=None,
                    jd_text="负责产品规划、用户研究和数据分析。",
                    apply_url="https://www.liepin.com/job/1976552102.shtml",
                    is_active=True,
                    jd_parsed={"live_posting": True, "market_region": "CN"},
                ),
            ]
        )
        session.commit()

    response = client.get("/api/v1/jobs/search?keyword=产品经理&city=北京&limit=2")

    assert response.status_code == 200
    jobs = response.json()["data"]["jobs"]
    assert jobs[0]["source"] == "liepin_mcp"
    assert jobs[0]["company"] == "猎聘实时公司"


def test_jobs_search_refreshes_liepin_mcp_when_keyword_results_are_sparse(monkeypatch) -> None:
    import app.services.job_service as job_service_module

    _reset_search_data()
    monkeypatch.setattr(job_service_module.settings, "enable_liepin_mcp", True)
    monkeypatch.setattr(job_service_module.settings, "liepin_mcp_token", "test-token")

    def fake_fetch_liepin_mcp_jobs(*, queries: str | None = None, limit_per_query: int | None = None, company: str | None = None):
        assert queries == "Java@上海"
        assert limit_per_query == 10
        assert company is None
        return [
            JobSourceRecord(
                external_id=f"liepin-mcp:java-shanghai-{index}",
                source="liepin_mcp",
                title=f"Java 后端开发工程师 {index}",
                company=f"上海科技公司{index}",
                city="上海",
                salary_range="20-35k",
                duration=None,
                jd_text="负责 Java、Spring、Redis 和微服务开发。",
                apply_url=f"https://www.liepin.com/job/java-shanghai-{index}.shtml",
                metadata={"source_adapter": "liepin_mcp", "live_posting": True, "market_region": "CN"},
            )
            for index in range(1, 9)
        ]

    monkeypatch.setattr(job_service_module, "fetch_liepin_mcp_jobs", fake_fetch_liepin_mcp_jobs)

    response = client.get("/api/v1/jobs/search?keyword=Java&city=上海&limit=10")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 8
    assert data["source_status"]["liepin_mcp"]["status"] == "ok"
    assert data["source_status"]["liepin_mcp"]["records"] == 8
    assert all(job["source"] == "liepin_mcp" for job in data["jobs"])


def test_jobs_search_matches_company_and_role_tokens_in_one_query(monkeypatch) -> None:
    import app.services.job_service as job_service_module

    _reset_search_data()
    monkeypatch.setattr(job_service_module, "fetch_tencent_jobs", lambda **_: [])
    with session_local() as session:
        session.add_all(
            [
                Job(
                    external_id="tencent-java-local",
                    source="official_company",
                    title="Java 后端开发工程师",
                    company="腾讯",
                    city="深圳",
                    salary_range="25-40k",
                    duration=None,
                    jd_text="负责 Java、Spring、Redis 和高并发服务开发。",
                    apply_url="https://careers.tencent.com/jobdesc.html?postId=tencent-java-local",
                    is_active=True,
                    jd_parsed={"live_posting": True, "market_region": "CN"},
                ),
                Job(
                    external_id="jd-java-local",
                    source="liepin_mcp",
                    title="Java 后端开发工程师",
                    company="京东",
                    city="北京",
                    salary_range="25-45k",
                    duration=None,
                    jd_text="负责 Java 服务端开发。",
                    apply_url="https://www.liepin.com/job/jd-java-local.shtml",
                    is_active=True,
                    jd_parsed={"live_posting": True, "market_region": "CN"},
                ),
                Job(
                    external_id="tencent-backend-local",
                    source="official_company",
                    title="后台开发工程师",
                    company="腾讯",
                    city="深圳",
                    salary_range="25-40k",
                    duration=None,
                    jd_text="负责服务端开发、接口、缓存和分布式系统。",
                    apply_url="https://careers.tencent.com/jobdesc.html?postId=tencent-backend-local",
                    is_active=True,
                    jd_parsed={"live_posting": True, "market_region": "CN"},
                ),
            ]
        )
        session.commit()

    response = client.get("/api/v1/jobs/search?keyword=腾讯Java&limit=10")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 2
    assert {job["company"] for job in data["jobs"]} == {"腾讯"}
    assert {job["title"] for job in data["jobs"]} == {"Java 后端开发工程师", "后台开发工程师"}


def test_jobs_search_expands_company_role_aliases_beyond_tencent(monkeypatch) -> None:
    import app.services.job_service as job_service_module

    _reset_search_data()
    monkeypatch.setattr(job_service_module.settings, "enable_liepin_mcp", False)
    monkeypatch.setattr(job_service_module, "fetch_tencent_jobs", lambda **_: [])
    with session_local() as session:
        session.add_all(
            [
                Job(
                    external_id="bytedance-ai-search",
                    source="liepin_mcp",
                    title="AI 搜索策略工程师",
                    company="字节跳动",
                    city="北京",
                    salary_range="30-50k",
                    duration=None,
                    jd_text="负责搜索排序、机器学习和大模型评估平台建设。",
                    apply_url="https://www.liepin.com/job/bytedance-ai-search.shtml",
                    is_active=True,
                    jd_parsed={"live_posting": True, "market_region": "CN"},
                ),
                Job(
                    external_id="alibaba-service",
                    source="liepin_mcp",
                    title="服务端研发工程师",
                    company="阿里云",
                    city="杭州",
                    salary_range="25-45k",
                    duration=None,
                    jd_text="负责 Java、分布式系统和云原生平台研发。",
                    apply_url="https://www.liepin.com/job/alibaba-service.shtml",
                    is_active=True,
                    jd_parsed={"live_posting": True, "market_region": "CN"},
                ),
                Job(
                    external_id="baidu-ai-search",
                    source="liepin_mcp",
                    title="AI 搜索策略工程师",
                    company="百度",
                    city="北京",
                    salary_range="25-45k",
                    duration=None,
                    jd_text="负责搜索推荐算法和机器学习模型。",
                    apply_url="https://www.liepin.com/job/baidu-ai-search.shtml",
                    is_active=True,
                    jd_parsed={"live_posting": True, "market_region": "CN"},
                ),
            ]
        )
        session.commit()

    bytedance_response = client.get("/api/v1/jobs/search?keyword=字节算法&limit=10")
    alibaba_response = client.get("/api/v1/jobs/search?keyword=阿里Java&limit=10")

    assert bytedance_response.status_code == 200
    bytedance_jobs = bytedance_response.json()["data"]["jobs"]
    assert len(bytedance_jobs) == 1
    assert bytedance_jobs[0]["company"] == "字节跳动"
    assert bytedance_jobs[0]["title"] == "AI 搜索策略工程师"

    assert alibaba_response.status_code == 200
    alibaba_jobs = alibaba_response.json()["data"]["jobs"]
    assert len(alibaba_jobs) == 1
    assert alibaba_jobs[0]["company"] == "阿里云"
    assert alibaba_jobs[0]["title"] == "服务端研发工程师"


def test_big_tech_search_refreshes_named_companies_instead_of_anonymous_large_company(monkeypatch) -> None:
    import app.services.job_service as job_service_module

    _reset_search_data()
    monkeypatch.setattr(job_service_module.settings, "enable_liepin_mcp", True)
    monkeypatch.setattr(job_service_module.settings, "liepin_mcp_token", "test-token")
    monkeypatch.setattr(job_service_module, "fetch_tencent_jobs", lambda **_: [])
    calls: list[tuple[str | None, str | None]] = []

    with session_local() as session:
        session.add(
            Job(
                external_id="liepin-mcp:anonymous-big-company-java",
                source="liepin_mcp",
                title="Java 开发工程师（大厂）",
                company="某大型通信设备公司",
                city="上海",
                salary_range="20-40k",
                duration=None,
                jd_text="负责 Java 开发。",
                apply_url="https://www.liepin.com/job/anonymous-big-company-java.shtml",
                is_active=True,
                jd_parsed={"live_posting": True, "market_region": "CN"},
            )
        )
        session.commit()

    def fake_fetch_liepin_mcp_jobs(*, queries: str | None = None, limit_per_query: int | None = None, company: str | None = None):
        calls.append((queries, company))
        if company not in {"腾讯", "阿里巴巴", "字节跳动", "百度", "美团"}:
            return []
        return [
            JobSourceRecord(
                external_id=f"liepin-mcp:{company}:java",
                source="liepin_mcp",
                title="Java 后端开发工程师",
                company=company,
                city="北京",
                salary_range="25-45k",
                duration=None,
                jd_text="负责 Java、Spring Cloud 和分布式服务开发。",
                apply_url=f"https://www.liepin.com/job/{company}-java.shtml",
                metadata={"source_adapter": "liepin_mcp", "live_posting": True, "market_region": "CN"},
            )
        ]

    monkeypatch.setattr(job_service_module, "fetch_liepin_mcp_jobs", fake_fetch_liepin_mcp_jobs)

    response = client.get("/api/v1/jobs/search?keyword=大厂Java&limit=10")

    assert response.status_code == 200
    data = response.json()["data"]
    companies = {job["company"] for job in data["jobs"]}
    assert {"腾讯", "阿里巴巴", "字节跳动"}.issubset(companies)
    assert "某大型通信设备公司" not in companies
    assert {company for _, company in calls}.issuperset({"腾讯", "阿里巴巴", "字节跳动"})
    assert data["source_status"]["liepin_mcp"]["records"] >= 5


def test_jobs_search_refreshes_tencent_official_for_company_role_query(monkeypatch) -> None:
    import app.services.job_service as job_service_module

    _reset_search_data()
    monkeypatch.setattr(job_service_module.settings, "enable_liepin_mcp", False)

    def fake_fetch_tencent_jobs(*, keywords: list[str] | None = None, page_size: int = 10):
        assert keywords is not None
        assert "Java" in keywords
        assert "后端" in keywords
        assert page_size == 10
        return [
            JobSourceRecord(
                external_id="official:tencent:java-live-1",
                source="official_company",
                title="Java 后端开发工程师",
                company="腾讯",
                city="深圳",
                salary_range=None,
                duration=None,
                jd_text="负责 Java、Spring、Redis 和分布式服务开发。",
                apply_url="https://careers.tencent.com/jobdesc.html?postId=java-live-1",
                metadata={
                    "source_adapter": "tencent_official",
                    "live_posting": True,
                    "market_region": "CN",
                },
            )
        ]

    monkeypatch.setattr(job_service_module, "fetch_tencent_jobs", fake_fetch_tencent_jobs)

    response = client.get("/api/v1/jobs/search?keyword=腾讯Java&limit=10")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 1
    assert data["jobs"][0]["company"] == "腾讯"
    assert data["jobs"][0]["title"] == "Java 后端开发工程师"
    assert data["source_status"]["tencent_official"]["status"] == "ok"
    assert data["source_status"]["tencent_official"]["records"] == 1


def test_job_detail_returns_full_display_and_interview_context_fields() -> None:
    _reset_search_data()
    with session_local() as session:
        session.add(
            Job(
                external_id="detail-product",
                source="seed",
                title="AI 产品经理实习生",
                company="腾讯",
                city="深圳",
                salary_range="250-320元/天",
                duration="6个月",
                jd_text="负责 AI 产品需求分析、用户研究、SQL 数据分析、原型设计和跨团队沟通。",
                apply_url="https://join.qq.com/post/detail-product",
                deadline=date(2026, 5, 10),
                is_active=True,
            )
        )
        session.commit()
        job_id = str(session.query(Job).filter(Job.external_id == "detail-product").one().id)

    response = client.get(f"/api/v1/jobs/{job_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["id"] == job_id
    assert data["title"] == "AI 产品经理实习生"
    assert data["company"] == "腾讯"
    assert data["city"] == "深圳"
    assert data["salary"] == "250-320元/天"
    assert data["job_type"] == "intern"
    assert data["job_type_label"] == "实习"
    assert data["market_region"] == "CN"
    assert "SQL" in data["skills"]
    assert "AI 产品需求分析" in data["jd_text"]
    assert data["interview_context"]["company"] == "腾讯"
    assert data["interview_context"]["job_type_label"] == "实习"
    assert "SQL" in data["interview_context"]["skills"]
    assert data["apply_url"].startswith("https://join.qq.com")


def test_jobs_search_unified_contract_city_limit_and_source_status() -> None:
    _reset_search_data()
    with session_local() as session:
        for index in range(4):
            session.add(
                Job(
                    external_id=f"official-product-{index}",
                    source="official_company",
                    title="产品经理实习生",
                    company=f"国内企业{index}",
                    city="北京",
                    salary_range="220-300元/天",
                    duration="6个月",
                    jd_text="负责产品经理相关工作、用户研究和 SQL 数据分析。",
                    apply_url=f"https://careers.example.cn/jobs/product-{index}",
                    deadline=date(2026, 5, 10),
                    is_active=True,
                )
            )
        session.add(
            Job(
                external_id="official-product-shanghai",
                source="official_company",
                title="产品经理实习生",
                company="上海企业",
                city="上海",
                salary_range="220-300元/天",
                duration="6个月",
                jd_text="负责产品经理相关工作。",
                apply_url="https://careers.example.cn/jobs/product-shanghai",
                deadline=date(2026, 5, 10),
                is_active=True,
            )
        )
        session.commit()

    response = client.get("/api/v1/jobs/search?keyword=产品经理&city=北京&limit=2")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 2
    assert data["source_status"]["boss"]["status"] in {"blocked", "disabled"}
    assert data["source_status"]["third_party_search"]["status"] in {"disabled", "ok"}
    for item in data["jobs"]:
        assert set(["job_id", "title", "company", "city", "apply_url", "source"]).issubset(item)
        assert item["city"] == "北京"
        assert item["job_id"] == item["id"]


def test_jobs_search_deduplicates_by_url_and_composite_key() -> None:
    _reset_search_data()
    with session_local() as session:
        session.add_all(
            [
                Job(
                    external_id="official-dup-url",
                    source="official_company",
                    title="Java后端开发工程师",
                    company="腾讯",
                    city="深圳",
                    salary_range="25-40k",
                    duration=None,
                    jd_text="负责 Java 后端、接口、数据库和 Redis。",
                    apply_url="https://join.qq.com/post/backend-java",
                    deadline=date(2026, 5, 1),
                    is_active=True,
                ),
                Job(
                    external_id="third-party-dup-url",
                    source="third_party_search",
                    title="后端研发工程师（Java）",
                    company="腾讯",
                    city="深圳",
                    salary_range="25-40k",
                    duration=None,
                    jd_text="负责 Java 后端服务。",
                    apply_url="https://join.qq.com/post/backend-java?from=search",
                    deadline=date(2026, 5, 2),
                    is_active=True,
                ),
                Job(
                    external_id="official-same-title-other-city",
                    source="official_company",
                    title="Java后端开发工程师",
                    company="腾讯",
                    city="北京",
                    salary_range="25-40k",
                    duration=None,
                    jd_text="负责 Java 后端服务。",
                    apply_url="https://join.qq.com/post/backend-java-beijing",
                    deadline=date(2026, 5, 2),
                    is_active=True,
                ),
            ]
        )
        session.commit()

    response = client.get("/api/v1/jobs/search?keyword=后端&limit=10")

    assert response.status_code == 200
    jobs = response.json()["data"]["jobs"]
    shenzhen_jobs = [job for job in jobs if job["company"] == "腾讯" and job["city"] == "深圳"]
    beijing_jobs = [job for job in jobs if job["company"] == "腾讯" and job["city"] == "北京"]
    assert len(shenzhen_jobs) == 1
    assert len(beijing_jobs) == 1
    assert set(shenzhen_jobs[0]["merged_sources"]) == {"official_company", "third_party_search"}
    assert shenzhen_jobs[0]["duplicate_count"] == 2
