from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text

from app.core.database import session_local
from app.scripts.sync_real_jobs import sync_real_jobs
from app.tools.job_sources import (
    JobSourceRecord,
    default_adapters,
    fetch_market_baseline_jobs,
    fetch_official_company_jobs,
    fetch_liepin_mcp_jobs,
    parse_ashby_payload,
    parse_greenhouse_payload,
    parse_liepin_mcp_payload,
    parse_tencent_payload,
)


def _reset_jobs() -> None:
    with session_local() as session:
        session.execute(text("DELETE FROM chat_sessions"))
        session.execute(text("DELETE FROM interview_sessions"))
        session.execute(text("DELETE FROM applications"))
        session.execute(text("DELETE FROM resumes"))
        session.execute(text("DELETE FROM jobs"))
        session.execute(text("DELETE FROM users"))
        session.commit()


def test_sync_real_jobs_upserts_real_apply_urls_and_disables_missing_records() -> None:
    _reset_jobs()

    def first_fetch() -> list[JobSourceRecord]:
        return [
            JobSourceRecord(
                external_id="ashby:notion:job-1",
                source="ashby",
                title="Software Engineer Intern",
                company="Notion",
                city="New York",
                salary_range="$40/hour",
                duration=None,
                jd_text="Build product experiences with Python and React.",
                apply_url="https://jobs.ashbyhq.com/notion/job-1",
                deadline=None,
            )
        ]

    result = sync_real_jobs(fetchers=[first_fetch])
    assert result["synced_jobs"] == 1

    with session_local() as session:
        row = session.execute(text("SELECT source, apply_url, is_active FROM jobs WHERE external_id='ashby:notion:job-1'")).mappings().one()
    assert row["source"] == "ashby"
    assert "example.com" not in row["apply_url"]
    assert row["is_active"] is True

    result = sync_real_jobs(fetchers=[lambda: []])
    assert result["synced_jobs"] == 0
    with session_local() as session:
        is_active = session.execute(text("SELECT is_active FROM jobs WHERE external_id='ashby:notion:job-1'")).scalar_one()
    assert is_active is False


def test_sync_real_jobs_accepts_real_ats_long_location_and_salary_text() -> None:
    _reset_jobs()
    long_city = "United States, Canada, United Kingdom, Germany, Netherlands, Remote Friendly"
    long_salary = "$120,000 - $180,000 USD plus equity, bonus, benefits, and location-based compensation details"

    def fetch_jobs() -> list[JobSourceRecord]:
        return [
            JobSourceRecord(
                external_id="ashby:ramp:long-location",
                source="ashby",
                title="Senior Product Manager, Growth Platform",
                company="Ramp",
                city=long_city,
                salary_range=long_salary,
                duration=None,
                jd_text="Own growth platform experiments and analytics.",
                apply_url="https://jobs.ashbyhq.com/ramp/long-location",
                deadline=None,
            )
        ]

    result = sync_real_jobs(fetchers=[fetch_jobs])

    assert result["synced_jobs"] == 1
    with session_local() as session:
        row = session.execute(text("SELECT city, salary_range FROM jobs WHERE external_id='ashby:ramp:long-location'")).mappings().one()
    assert row["city"] == long_city
    assert row["salary_range"] == long_salary


def test_sync_real_jobs_deduplicates_records_and_reports_source_status() -> None:
    _reset_jobs()

    def fetch_jobs() -> list[JobSourceRecord]:
        return [
            JobSourceRecord(
                external_id="official:bytedance:pm-1",
                source="official_company",
                title="产品经理实习生",
                company="字节跳动",
                city="北京",
                salary_range="220-300元/天",
                duration="6个月",
                jd_text="负责产品需求、用户研究和 SQL 数据分析。",
                apply_url="https://jobs.bytedance.com/zh/position/pm-1",
                deadline=None,
            ),
            JobSourceRecord(
                external_id="third-party:bytedance:pm-1",
                source="third_party_search",
                title="产品经理实习生",
                company="字节跳动",
                city="北京",
                salary_range="220-300元/天",
                duration=None,
                jd_text="第三方搜索结果：产品需求和 SQL 分析。",
                apply_url="https://jobs.bytedance.com/zh/position/pm-1?from=search",
                deadline=None,
            ),
        ]

    result = sync_real_jobs(fetchers=[fetch_jobs])

    assert result["synced_jobs"] == 1
    assert result["source_status"]["custom"]["status"] == "ok"
    with session_local() as session:
        rows = session.execute(text("SELECT source, jd_parsed FROM jobs")).mappings().all()
    assert len(rows) == 1
    assert rows[0]["source"] == "official_company"
    assert set(rows[0]["jd_parsed"]["merged_sources"]) == {"official_company", "third_party_search"}


def test_market_baseline_covers_mainstream_interview_roles() -> None:
    records = fetch_market_baseline_jobs()
    industries = {record.metadata.get("industry") for record in records}

    assert len(records) >= 30
    assert len(industries) >= 10
    assert all(record.source == "market_baseline" for record in records)
    assert all(record.apply_url for record in records)


def test_domestic_product_manager_search_has_multiple_beijing_candidates() -> None:
    records = fetch_official_company_jobs() + fetch_market_baseline_jobs()
    matches = [
        record
        for record in records
        if record.city == "北京" and "产品经理" in " ".join([record.title, record.jd_text or ""])
    ]

    assert len(matches) >= 5
    assert len({record.company for record in matches}) >= 5
    assert all(record.apply_url and "example.com" not in record.apply_url for record in matches)


def test_default_adapters_prioritize_domestic_sources_without_global_ats() -> None:
    names = [adapter.name for adapter in default_adapters()]

    assert "tencent_official" in names
    assert "official_company_catalog" in names
    assert "public_board" in names
    assert not any(name.startswith("ashby:") for name in names)
    assert not any(name.startswith("greenhouse:") for name in names)
    assert not any(name.startswith("lever:") for name in names)


def test_liepin_mcp_adapter_is_configurable_and_disabled_without_token(monkeypatch) -> None:
    import app.tools.job_sources as job_sources

    monkeypatch.setattr(job_sources.settings, "enable_liepin_mcp", True)
    monkeypatch.setattr(job_sources.settings, "liepin_mcp_url", "https://open-agent.liepin.com/mcp/user")
    monkeypatch.setattr(job_sources.settings, "liepin_mcp_token", None)

    adapter = next(item for item in default_adapters() if item.name == "liepin_mcp")

    assert adapter.enabled is False
    assert "LIEPIN_MCP_TOKEN" in (adapter.disabled_reason or "")


def test_liepin_mcp_payload_maps_to_authorized_job_records() -> None:
    records = parse_liepin_mcp_payload(
        {
            "jobs": [
                {
                    "job_id": "lp-1001",
                    "title": "AI 产品经理实习生",
                    "company": "猎聘示例科技",
                    "city": "北京",
                    "salary": "250-350元/天",
                    "description": "负责 AIGC 产品调研、SQL 数据分析和需求管理。",
                    "url": "https://www.liepin.com/job/lp-1001.shtml",
                    "posted_at": "2026-05-01T10:00:00",
                }
            ]
        },
        query_keyword="AI 产品经理",
        query_city="北京",
    )

    assert len(records) == 1
    record = records[0]
    assert record.external_id == "liepin-mcp:lp-1001"
    assert record.source == "liepin_mcp"
    assert record.title == "AI 产品经理实习生"
    assert record.company == "猎聘示例科技"
    assert record.city == "北京"
    assert record.salary_range == "250-350元/天"
    assert record.apply_url == "https://www.liepin.com/job/lp-1001.shtml"
    assert "AIGC" in record.jd_text
    assert record.metadata["source_adapter"] == "liepin_mcp"
    assert record.metadata["authorized_mcp"] is True


def test_liepin_mcp_payload_accepts_real_tool_field_names() -> None:
    records = parse_liepin_mcp_payload(
        {
            "data": {
                "list": [
                    {
                        "jobId": 76552101,
                        "jobType": "2",
                        "jobName": "产品经理",
                        "company": "猎聘字段示例公司",
                        "location": "北京-朝阳区",
                        "salary": "20-35k",
                        "education": "本科",
                        "workYears": "3-5年",
                        "industry": "互联网",
                        "jobDetailUrl": "https://www.liepin.com/job/1976552101.shtml?mscid=soai_pc_001",
                    }
                ]
            }
        },
        query_keyword="产品经理",
        query_city="北京",
    )

    assert len(records) == 1
    record = records[0]
    assert record.external_id == "liepin-mcp:76552101"
    assert record.company == "猎聘字段示例公司"
    assert record.city == "北京-朝阳区"
    assert record.salary_range == "20-35k"
    assert record.apply_url.startswith("https://www.liepin.com/job/1976552101.shtml")
    assert "3-5年" in record.jd_text


def test_fetch_liepin_mcp_jobs_uses_client_and_query_plan() -> None:
    class FakeClient:
        def search_jobs(self, *, keyword: str, city: str | None, limit: int, company: str | None = None) -> dict:
            assert keyword == "产品经理"
            assert city == "北京"
            assert limit == 2
            assert company is None
            return {
                "list": [
                    {
                        "id": "lp-2001",
                        "jobName": "产品经理",
                        "companyName": "国内互联网公司",
                        "workCity": "北京",
                        "salaryText": "20-35k",
                        "jobDescription": "负责用户增长、SQL 分析和产品规划。",
                        "jobUrl": "https://www.liepin.com/job/lp-2001.shtml",
                    }
                ]
            }

    records = fetch_liepin_mcp_jobs(client=FakeClient(), queries="产品经理@北京", limit_per_query=2)

    assert len(records) == 1
    assert records[0].external_id == "liepin-mcp:lp-2001"
    assert records[0].metadata["query_keyword"] == "产品经理"
    assert records[0].metadata["query_city"] == "北京"


def test_fetch_liepin_mcp_jobs_can_pass_company_filter() -> None:
    class FakeClient:
        def search_jobs(self, *, keyword: str, city: str | None, limit: int, company: str | None = None) -> dict:
            assert keyword == "Java"
            assert city == "深圳"
            assert company == "腾讯"
            assert limit == 5
            return {
                "list": [
                    {
                        "id": "lp-tencent-java",
                        "jobName": "Java 后端开发工程师",
                        "companyName": "腾讯",
                        "workCity": "深圳",
                        "salaryText": "25-45k",
                        "jobDescription": "负责 Java、Redis 和分布式系统。",
                        "jobUrl": "https://www.liepin.com/job/lp-tencent-java.shtml",
                    }
                ]
            }

    records = fetch_liepin_mcp_jobs(client=FakeClient(), queries="Java@深圳", limit_per_query=5, company="腾讯")

    assert len(records) == 1
    assert records[0].company == "腾讯"
    assert records[0].metadata["query_company"] == "腾讯"


def test_build_liepin_tool_arguments_maps_company_schema_field() -> None:
    from app.tools.job_sources import _build_liepin_tool_arguments

    args = _build_liepin_tool_arguments(
        {
            "properties": {
                "jobName": {"type": "string"},
                "companyName": {"type": "string"},
                "city": {"type": "string"},
                "pageSize": {"type": "integer"},
            },
            "required": ["jobName"],
        },
        keyword="Java",
        company="腾讯",
        city="深圳",
        limit=10,
    )

    assert args["jobName"] == "Java"
    assert args["companyName"] == "腾讯"
    assert args["city"] == "深圳"
    assert args["pageSize"] == 10


def test_fetch_liepin_mcp_jobs_reports_business_error() -> None:
    class FakeClient:
        def search_jobs(self, *, keyword: str, city: str | None, limit: int, company: str | None = None) -> dict:
            return {"code": 429001, "msg": "请求过于频繁，请稍后再试", "data": {"result": "请求过于频繁，请稍后再试"}}

    with pytest.raises(RuntimeError, match="请求过于频繁"):
        fetch_liepin_mcp_jobs(client=FakeClient(), queries="Java@北京", limit_per_query=10)


def test_sync_real_jobs_accepts_liepin_mcp_records_and_reports_status() -> None:
    _reset_jobs()

    result = sync_real_jobs(
        fetchers=[
            lambda: parse_liepin_mcp_payload(
                {
                    "jobs": [
                        {
                            "id": "lp-3001",
                            "title": "Java 后端开发工程师",
                            "company": "猎聘真实公司",
                            "city": "深圳",
                            "salary": "25-40k",
                            "jd": "负责 Java、Redis、微服务和数据库建设。",
                            "apply_url": "https://www.liepin.com/job/lp-3001.shtml",
                        }
                    ]
                }
            )
        ]
    )

    assert result["synced_jobs"] == 1
    assert result["source_status"]["custom"]["status"] == "ok"
    with session_local() as session:
        row = session.execute(text("SELECT source, apply_url, jd_parsed FROM jobs WHERE external_id='liepin-mcp:lp-3001'")).mappings().one()
    assert row["source"] == "liepin_mcp"
    assert row["apply_url"].startswith("https://www.liepin.com/job/")
    assert row["jd_parsed"]["source_adapter"] == "liepin_mcp"


def test_sync_real_jobs_can_skip_deactivation_for_on_demand_refresh() -> None:
    _reset_jobs()

    sync_real_jobs(
        fetchers=[
            lambda: [
                JobSourceRecord(
                    external_id="liepin-mcp:old-java",
                    source="liepin_mcp",
                    title="Java 开发工程师",
                    company="老岗位公司",
                    city="上海",
                    salary_range="20-30k",
                    duration=None,
                    jd_text="Java Redis Spring",
                    apply_url="https://www.liepin.com/job/old-java.shtml",
                    metadata={"source_adapter": "liepin_mcp", "live_posting": True},
                )
            ]
        ]
    )
    result = sync_real_jobs(
        fetchers=[
            lambda: [
                JobSourceRecord(
                    external_id="liepin-mcp:new-java",
                    source="liepin_mcp",
                    title="Java 后端工程师",
                    company="新岗位公司",
                    city="上海",
                    salary_range="25-40k",
                    duration=None,
                    jd_text="Java Spring Cloud",
                    apply_url="https://www.liepin.com/job/new-java.shtml",
                    metadata={"source_adapter": "liepin_mcp", "live_posting": True},
                )
            ]
        ],
        deactivate_missing=False,
    )

    assert result["synced_jobs"] == 1
    assert result["disabled_jobs"] == 0
    with session_local() as session:
        rows = session.execute(text("SELECT external_id, is_active FROM jobs WHERE source='liepin_mcp' ORDER BY external_id")).mappings().all()
    assert [(row["external_id"], row["is_active"]) for row in rows] == [
        ("liepin-mcp:new-java", True),
        ("liepin-mcp:old-java", True),
    ]


def test_tencent_public_payload_maps_to_official_company_records() -> None:
    records = parse_tencent_payload(
        {
            "Code": 200,
            "Data": {
                "Posts": [
                    {
                        "PostId": "1972141322328498176",
                        "RecruitPostName": "AI平台产品高级产品经理",
                        "LocationName": "深圳",
                        "ProductName": "音视频PaaS",
                        "CategoryName": "产品",
                        "Responsibility": "负责AI产品规划、用户研究和数据分析。",
                        "Requirement": "熟悉 SQL、AIGC 产品和跨团队协作。",
                        "LastUpdateTime": "2026年04月01日",
                        "PostURL": "http://careers.tencent.com/jobdesc.html?postId=1972141322328498176",
                        "RequireWorkYearsName": "三年以上工作经验",
                    }
                ]
            },
        }
    )

    assert len(records) == 1
    record = records[0]
    assert record.external_id == "official:tencent:1972141322328498176"
    assert record.source == "official_company"
    assert record.company == "腾讯"
    assert record.city == "深圳"
    assert record.apply_url == "https://careers.tencent.com/jobdesc.html?postId=1972141322328498176"
    assert "AIGC" in record.jd_text
    assert record.posted_at is not None
    assert record.metadata["source_adapter"] == "tencent_official"
    assert record.metadata["public_access"] is True


def test_official_company_catalog_covers_domestic_public_entry_points() -> None:
    records = fetch_official_company_jobs()
    companies = {record.company for record in records}
    industries = {record.metadata.get("industry") for record in records}

    assert len(records) >= 24
    assert len(companies) >= 18
    assert len(industries) >= 8
    assert all(record.source == "official_company" for record in records)
    assert all(record.metadata.get("public_access") is True for record in records)
    assert all(record.metadata.get("login_required") is False for record in records)
    assert all(record.apply_url and record.apply_url.startswith("https://") for record in records)
    assert all("example.com" not in record.apply_url for record in records)


def test_ashby_and_greenhouse_payloads_are_mapped_to_common_records() -> None:
    ashby_records = parse_ashby_payload(
        board="notion",
        payload={
            "jobs": [
                {
                    "id": "a1",
                    "title": "Product Intern",
                    "location": "San Francisco",
                    "jobUrl": "https://jobs.ashbyhq.com/notion/a1",
                    "descriptionPlain": "Work with product and data teams.",
                    "compensation": {"compensationTierSummary": "$30/hour"},
                }
            ]
        },
    )
    greenhouse_records = parse_greenhouse_payload(
        board="airbnb",
        payload={
            "jobs": [
                {
                    "id": 42,
                    "title": "Data Intern",
                    "absolute_url": "https://boards.greenhouse.io/airbnb/jobs/42",
                    "location": {"name": "Remote"},
                    "content": "<p>Analyze marketplace data.</p>",
                }
            ]
        },
    )

    assert ashby_records[0].external_id == "ashby:notion:a1"
    assert ashby_records[0].source == "ashby"
    assert ashby_records[0].apply_url.startswith("https://jobs.ashbyhq.com/")
    assert ashby_records[0].salary_range == "$30/hour"
    assert greenhouse_records[0].external_id == "greenhouse:airbnb:42"
    assert greenhouse_records[0].source == "greenhouse"
    assert greenhouse_records[0].jd_text == "Analyze marketplace data."
