"""Job source adapters for public job ingestion."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from html import unescape
from typing import Any, Callable
from urllib.parse import quote_plus, urlparse

import httpx

from app.core.settings import settings


@dataclass
class JobSourceRecord:
    """Unified job record emitted by every source adapter."""

    external_id: str
    source: str
    title: str
    company: str
    city: str | None
    salary_range: str | None
    duration: str | None
    jd_text: str | None
    apply_url: str | None
    deadline: date | None = None
    posted_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class JobSourceAdapter:
    """Small adapter wrapper used by the sync script."""

    name: str
    fetch: Callable[[], list[JobSourceRecord]]
    source_type: str
    enabled: bool = True
    disabled_reason: str | None = None


FetchFn = Callable[[], list[JobSourceRecord]]


DEFAULT_ASHBY_BOARDS = ["notion", "ramp", "cursor"]
DEFAULT_GREENHOUSE_BOARDS = ["airbnb", "databricks"]
DEFAULT_LEVER_BOARDS = ["scaleai"]
TENCENT_DEFAULT_KEYWORDS = ["产品", "后端", "Java", "前端", "测试", "数据", "运营", "市场", "算法"]
LIEPIN_MCP_DEFAULT_URL = "https://open-agent.liepin.com/mcp/user"

RESTRICTED_PLATFORM_STATUS: dict[str, dict[str, str]] = {
    "boss": {"status": "blocked", "reason": "BOSS search pages rely on browser verification and anti-bot controls."},
    "liepin": {"status": "blocked", "reason": "Liepin web pages remain blocked for unauthenticated scraping; use the authorized Liepin MCP adapter instead."},
    "zhaopin": {"status": "blocked", "reason": "Zhaopin search pages are JS-heavy and not exposed as a stable public API."},
    "51job": {"status": "blocked", "reason": "51job public search returns anti-crawler/JS shell pages in backend probes."},
    "lagou": {"status": "blocked", "reason": "Lagou search redirects to slider verification for automated traffic."},
}


class LiepinMcpClient:
    """Minimal streamable-HTTP MCP client for the authorized Liepin job tool."""

    def __init__(
        self,
        *,
        url: str,
        token: str,
        tool_name: str | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        self.url = url
        self.token = token
        self.tool_name = tool_name
        self.timeout_seconds = timeout_seconds
        self._session_id: str | None = None
        self._initialized = False
        self._selected_tool: dict[str, Any] | None = None

    def search_jobs(self, *, keyword: str, city: str | None, limit: int, company: str | None = None) -> dict[str, Any] | list[Any]:
        self._ensure_initialized()
        tool = self._selected_tool or self._select_tool(self._list_tools())
        arguments = _build_liepin_tool_arguments(tool.get("inputSchema") or tool.get("input_schema") or {}, keyword=keyword, company=company, city=city, limit=limit)
        payload = self._rpc("tools/call", {"name": tool["name"], "arguments": arguments})
        return _extract_mcp_tool_payload(payload)

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        init_payload = self._rpc(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "qingcheng-ai", "version": "0.1.0"},
            },
        )
        if isinstance(init_payload, dict):
            server_info = init_payload.get("serverInfo") or {}
            self._selected_tool = None
            self._server_name = server_info.get("name")
        self._notify_initialized()
        self._initialized = True

    def _notify_initialized(self) -> None:
        body = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        response = httpx.post(self.url, headers=self._headers(), json=body, timeout=self.timeout_seconds)
        if response.status_code not in {200, 202, 204}:
            response.raise_for_status()

    def _list_tools(self) -> list[dict[str, Any]]:
        payload = self._rpc("tools/list", {})
        tools = payload.get("tools") if isinstance(payload, dict) else None
        if not isinstance(tools, list):
            raise ValueError("Liepin MCP tools/list did not return a tools array.")
        return [tool for tool in tools if isinstance(tool, dict) and tool.get("name")]

    def _select_tool(self, tools: list[dict[str, Any]]) -> dict[str, Any]:
        if self.tool_name:
            for tool in tools:
                if tool.get("name") == self.tool_name:
                    self._selected_tool = tool
                    return tool
            raise ValueError(f"Configured Liepin MCP tool '{self.tool_name}' was not found.")
        selected = _select_liepin_search_tool(tools)
        self._selected_tool = selected
        return selected

    def _rpc(self, method: str, params: dict[str, Any]) -> Any:
        body = {"jsonrpc": "2.0", "id": _slug(f"{method}-{datetime.utcnow().isoformat()}"), "method": method, "params": params}
        response = httpx.post(self.url, headers=self._headers(), json=body, timeout=self.timeout_seconds)
        if response.headers.get("mcp-session-id"):
            self._session_id = response.headers["mcp-session-id"]
        response.raise_for_status()
        payload = _parse_mcp_http_response(response)
        if isinstance(payload, dict) and payload.get("error"):
            error = payload["error"]
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise RuntimeError(f"Liepin MCP error: {message}")
        return payload.get("result") if isinstance(payload, dict) and "result" in payload else payload

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "x-user-token": self.token,
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers


def fetch_ashby_jobs(board: str) -> list[JobSourceRecord]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true"
    response = httpx.get(url, timeout=20)
    response.raise_for_status()
    return parse_ashby_payload(board=board, payload=response.json())


def fetch_greenhouse_jobs(board: str) -> list[JobSourceRecord]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
    response = httpx.get(url, timeout=20)
    response.raise_for_status()
    return parse_greenhouse_payload(board=board, payload=response.json())


def fetch_lever_jobs(board: str) -> list[JobSourceRecord]:
    url = f"https://api.lever.co/v0/postings/{board}?mode=json"
    response = httpx.get(url, timeout=20)
    response.raise_for_status()
    return parse_lever_payload(board=board, payload=response.json())


def fetch_tencent_jobs(*, keywords: list[str] | None = None, page_size: int = 10) -> list[JobSourceRecord]:
    """Fetch public Tencent careers posts without login."""
    records: dict[str, JobSourceRecord] = {}
    for keyword in keywords or TENCENT_DEFAULT_KEYWORDS:
        url = "https://careers.tencent.com/tencentcareer/api/post/Query"
        params = {
            "timestamp": int(datetime.utcnow().timestamp() * 1000),
            "countryId": "",
            "cityId": "",
            "bgIds": "",
            "productId": "",
            "categoryId": "",
            "parentCategoryId": "",
            "attrId": "",
            "keyword": keyword,
            "pageIndex": 1,
            "pageSize": page_size,
            "language": "zh-cn",
            "area": "cn",
        }
        response = httpx.get(url, params=params, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        for record in parse_tencent_payload(response.json()):
            records[record.external_id] = record
    return list(records.values())


def parse_tencent_payload(payload: dict[str, Any]) -> list[JobSourceRecord]:
    """Map Tencent public career API payload to JobSourceRecord."""
    if int(payload.get("Code") or 0) != 200:
        return []
    posts = ((payload.get("Data") or {}).get("Posts") or []) if isinstance(payload.get("Data"), dict) else []
    records: list[JobSourceRecord] = []
    for item in posts:
        post_id = _safe_text(item.get("PostId") or item.get("RecruitPostId"))
        title = _safe_text(item.get("RecruitPostName"))
        if not post_id or not title:
            continue
        city = _safe_text(item.get("LocationName")) or None
        product = _safe_text(item.get("ProductName"))
        category = _safe_text(item.get("CategoryName"))
        work_years = _safe_text(item.get("RequireWorkYearsName"))
        responsibility = _clean_text(item.get("Responsibility"))
        requirement = _clean_text(item.get("Requirement"))
        jd_parts = [
            f"岗位方向：{category}" if category else "",
            f"产品/业务线：{product}" if product else "",
            f"经验要求：{work_years}" if work_years else "",
            responsibility,
            requirement,
        ]
        raw_url = _safe_text(item.get("PostURL"))
        apply_url = _https_url(raw_url) or f"https://careers.tencent.com/jobdesc.html?postId={post_id}"
        records.append(
            JobSourceRecord(
                external_id=f"official:tencent:{post_id}",
                source="official_company",
                title=title,
                company="腾讯",
                city=city,
                salary_range=None,
                duration=None,
                jd_text="\n".join(part for part in jd_parts if part),
                apply_url=apply_url,
                deadline=None,
                posted_at=_parse_cn_date(item.get("LastUpdateTime")) or _parse_datetime(item.get("LastUpdateTime")),
                metadata={
                    "source_type": "official_company",
                    "source_adapter": "tencent_official",
                    "public_access": True,
                    "login_required": False,
                    "live_posting": True,
                    "market_region": "CN",
                    "industry": "互联网/科技",
                    "function": category or _infer_function(title),
                    "product_name": product,
                    "work_years": work_years,
                },
            )
        )
    return records


def fetch_official_company_jobs() -> list[JobSourceRecord]:
    """Curated domestic official career entry catalog.

    These records point to public company career/campus pages. They do not require
    login to view the entry page, but some companies may require login only when
    the user starts an application on the original site.
    """
    rows = [
        ("official:bytedance:product", "产品经理实习生", "字节跳动", "北京", "220-300元/天", "https://jobs.bytedance.com/zh/position?keywords=%E4%BA%A7%E5%93%81", "互联网/科技", "产品"),
        ("official:baidu:ai-product", "AI 产品经理", "百度", "北京", "25-45k", "https://talent.baidu.com/jobs/list", "互联网/科技", "AI 产品"),
        ("official:kuaishou:commercial-product", "商业产品经理", "快手", "北京", "25-45k", "https://zhaopin.kuaishou.cn/", "互联网/科技", "商业产品"),
        ("official:xiaomi:iot-product", "IoT 产品经理", "小米", "北京", "20-35k", "https://hr.xiaomi.com/", "智能硬件", "IoT 产品"),
        ("official:huawei:cloud-product", "云产品经理", "华为", "北京", "25-45k", "https://career.huawei.com/reccampportal/portal5/index.html", "云计算", "云产品"),
        ("official:jd:product", "产品经理管培生", "京东", "北京", "12-20k", "https://campus.jd.com/", "消费零售", "产品"),
        ("official:tencent:backend", "后端开发工程师", "腾讯", "深圳", "25-40k", "https://careers.tencent.com/", "互联网/科技", "后端"),
        ("official:alibaba:data", "数据分析师", "阿里巴巴", "杭州", "20-35k", "https://talent.alibaba.com/", "互联网/科技", "数据"),
        ("official:meituan:operations", "商业运营专员", "美团", "上海", "15-25k", "https://zhaopin.meituan.com/web/position", "互联网/科技", "运营"),
        ("official:bilibili:content-operation", "内容运营实习生", "哔哩哔哩", "上海", "180-260元/天", "https://jobs.bilibili.com/", "内容社区", "内容运营"),
        ("official:netease:data-product", "数据产品经理", "网易", "杭州", "18-30k", "https://hr.163.com/", "互联网/科技", "数据产品"),
        ("official:xiaohongshu:growth", "增长产品实习生", "小红书", "上海", "220-300元/天", "https://job.xiaohongshu.com/", "内容社区", "增长产品"),
        ("official:cmb:risk", "风险管理岗", "招商银行", "深圳", "15-25k", "https://career.cmbchina.com/", "金融", "风控"),
        ("official:icbc:fintech", "金融科技岗", "工商银行", "北京", "面议", "https://job.icbc.com.cn/", "金融", "金融科技"),
        ("official:ccb:data", "数据分析岗", "建设银行", "北京", "面议", "https://job.ccb.com/", "金融", "数据"),
        ("official:boc:campus", "银行校招生", "中国银行", "北京", "面议", "https://campus.chinahr.com/pages/2024-boc", "金融", "校招"),
        ("official:cicc:ibd", "投行分析师", "中金公司", "北京", "20-35k", "https://www.cicc.com/careers/", "金融", "投行"),
        ("official:htsc:research", "行业研究员", "华泰证券", "上海", "18-35k", "https://job.htsc.com.cn/", "金融", "研究"),
        ("official:deloitte:consulting", "战略咨询顾问", "德勤咨询", "上海", "15-28k", "https://www2.deloitte.com/cn/zh/careers.html", "咨询", "战略咨询"),
        ("official:pwc:audit", "审计/咨询校招岗", "普华永道", "上海", "面议", "https://www.pwccn.com/zh/careers.html", "咨询", "审计咨询"),
        ("official:kpmg:consulting", "管理咨询顾问", "毕马威", "北京", "面议", "https://kpmg.com/cn/zh/home/careers.html", "咨询", "管理咨询"),
        ("official:ey:campus", "商业咨询校招岗", "安永", "上海", "面议", "https://www.ey.com/zh_cn/careers", "咨询", "商业咨询"),
        ("official:sgcc:digital", "数字化转型岗", "国家电网", "北京", "面议", "https://zhaopin.sgcc.com.cn/", "央国企", "数字化"),
        ("official:cmcc:product", "5G 产品运营岗", "中国移动", "北京", "面议", "https://job.10086.cn/", "央国企", "产品运营"),
        ("official:ct:cloud", "云网工程师", "中国电信", "广州", "面议", "https://job.chinatelecom.com.cn/", "央国企", "云网工程"),
        ("official:sinopec:campus", "能源行业管培生", "中国石化", "北京", "面议", "https://job.sinopec.com/", "央国企", "管培生"),
        ("official:byd:supply-chain", "供应链管理岗", "比亚迪", "深圳", "12-22k", "https://job.byd.com/", "制造/新能源", "供应链"),
        ("official:nio:ux", "用户体验研究员", "蔚来", "上海", "18-30k", "https://nio.jobs.feishu.cn/", "制造/新能源", "用户研究"),
        ("official:li:auto", "智能座舱产品经理", "理想汽车", "北京", "25-45k", "https://www.lixiang.com/employ.html", "制造/新能源", "智能产品"),
        ("official:geely:data", "数据分析工程师", "吉利汽车", "杭州", "15-28k", "https://campus.geely.com/", "制造/新能源", "数据"),
        ("official:pg:marketing", "品牌市场管培生", "宝洁", "广州", "面议", "https://www.pgcareers.com.cn/", "消费零售", "品牌市场"),
        ("official:loreal:marketing", "品牌市场实习生", "欧莱雅", "上海", "180-260元/天", "https://careers.loreal.com/zh_CN/content/China", "消费零售", "品牌市场"),
        ("official:unilever:ecommerce", "电商运营管培生", "联合利华", "上海", "面议", "https://careers.unilever.com/china", "消费零售", "电商运营"),
        ("official:nike:retail", "零售运营管理培训生", "耐克", "上海", "面议", "https://jobs.nike.com/zh-cn/", "消费零售", "零售运营"),
        ("official:astrazeneca:market", "医药市场专员", "阿斯利康", "上海", "面议", "https://careers.astrazeneca.com/", "医药健康", "市场"),
        ("official:roche:clinical", "临床运营专员", "罗氏", "北京", "面议", "https://careers.roche.com/global/en/china", "医药健康", "临床运营"),
        ("official:pfizer:medical", "医学信息沟通专员", "辉瑞", "广州", "面议", "https://www.pfizer.com.cn/careers", "医药健康", "医学沟通"),
        ("official:youdao:teaching", "教研运营", "网易有道", "杭州", "12-22k", "https://campus.youdao.com/", "教育", "教研运营"),
    ]
    return [
        _record(
            external_id=external_id,
            source="official_company",
            title=title,
            company=company,
            city=city,
            salary=salary,
            url=url,
            industry=industry,
            function=function,
            metadata={
                "source_type": "official_company",
                "source_adapter": "official_company_catalog",
                "public_access": True,
                "login_required": False,
                "live_posting": False,
                "market_region": "CN",
            },
        )
        for external_id, title, company, city, salary, url, industry, function in rows
    ]


def fetch_public_board_jobs() -> list[JobSourceRecord]:
    rows = [
        ("public-board:iguopin:digital-product", "央企数字化产品岗", "国聘公开岗位", "北京", "面议", "https://www.iguopin.com/", "央国企", "产品"),
        ("public-board:ncss:campus-data", "校招数据分析岗", "国家大学生就业服务平台", "全国", "面议", "https://www.ncss.cn/student/jobs/index.html", "校招", "数据"),
        ("public-board:mohrss:public-affairs", "公共事务岗", "人社部公开招聘公告", "北京", "面议", "https://www.mohrss.gov.cn/", "公共部门", "职能"),
        ("public-board:sasac:central-enterprise", "央企管培生", "国资委公开招聘公告", "全国", "面议", "http://www.sasac.gov.cn/", "央国企", "管培生"),
        ("public-board:state-grid:campus", "电网校招技术岗", "国家电网招聘平台", "全国", "面议", "https://zhaopin.sgcc.com.cn/", "央国企", "工程技术"),
        ("public-board:bank-campus", "银行校招综合岗", "银行公开招聘公告", "全国", "面议", "https://job.icbc.com.cn/", "金融", "校招"),
    ]
    return [
        _record(
            external_id=external_id,
            source="public_board",
            title=title,
            company=company,
            city=city,
            salary=salary,
            url=url,
            industry=industry,
            function=function,
            metadata={
                "source_type": "public_board",
                "source_adapter": "public_board_catalog",
                "public_access": True,
                "login_required": False,
                "live_posting": False,
                "market_region": "CN",
            },
        )
        for external_id, title, company, city, salary, url, industry, function in rows
    ]


def fetch_market_baseline_jobs() -> list[JobSourceRecord]:
    rows = [
        ("互联网/科技", "产品经理", "北京", "https://jobs.bytedance.com/zh/position?keywords=%E4%BA%A7%E5%93%81"),
        ("互联网/科技", "产品运营", "上海", "https://zhaopin.meituan.com/web/position"),
        ("互联网/科技", "用户运营", "北京", "https://www.zhihu.com/careers"),
        ("互联网/科技", "内容运营", "上海", "https://jobs.bilibili.com/"),
        ("工程技术", "后端开发工程师", "深圳", "https://careers.tencent.com/"),
        ("工程技术", "前端开发工程师", "上海", "https://jobs.bilibili.com/"),
        ("工程技术", "测试开发工程师", "杭州", "https://talent.alibaba.com/"),
        ("工程技术", "运维开发工程师", "北京", "https://campus.jd.com/"),
        ("数据与算法", "数据分析师", "杭州", "https://talent.alibaba.com/"),
        ("数据与算法", "算法工程师", "北京", "https://zhaopin.kuaishou.cn/"),
        ("数据与算法", "数据产品经理", "上海", "https://hr.163.com/"),
        ("数据与算法", "商业分析师", "北京", "https://careers.bcg.com/"),
        ("金融", "投行分析师", "北京", "https://www.cicc.com/careers/"),
        ("金融", "行业研究员", "上海", "https://job.htsc.com.cn/"),
        ("金融", "风险管理岗", "深圳", "https://career.cmbchina.com/"),
        ("金融", "基金运营岗", "广州", "https://www.efunds.com.cn/"),
        ("咨询", "管理咨询顾问", "上海", "https://www.mckinsey.com/careers/search-jobs"),
        ("咨询", "战略分析师", "上海", "https://www2.deloitte.com/cn/zh/careers.html"),
        ("咨询", "咨询研究员", "北京", "https://www.bain.com/careers/"),
        ("制造/新能源", "供应链管理岗", "深圳", "https://career.huawei.com/"),
        ("制造/新能源", "质量工程师", "苏州", "https://www.bosch.com.cn/careers/"),
        ("制造/新能源", "工艺工程师", "上海", "https://www.siemens.com/cn/zh/company/jobs.html"),
        ("消费零售", "品牌市场专员", "上海", "https://www.loreal.com/zh-cn/china/pages/careers/"),
        ("消费零售", "电商运营", "杭州", "https://campus.jd.com/"),
        ("消费零售", "渠道销售", "广州", "https://www.pgcareers.com.cn/"),
        ("医药健康", "医药市场专员", "上海", "https://careers.astrazeneca.com/"),
        ("医药健康", "临床运营专员", "北京", "https://careers.roche.com/global/en/china"),
        ("教育", "课程产品经理", "北京", "https://hr.163.com/"),
        ("教育", "教研运营", "杭州", "https://campus.youdao.com/"),
        ("央国企", "数字化转型岗", "北京", "https://www.iguopin.com/"),
        ("央国企", "财务管理岗", "上海", "https://www.iguopin.com/"),
        ("职能", "人力资源专员", "上海", "https://www.pwccn.com/zh/careers.html"),
        ("职能", "法务合规岗", "北京", "https://www2.deloitte.com/cn/zh/careers.html"),
        ("设计", "用户体验设计师", "深圳", "https://careers.tencent.com/"),
    ]
    records: list[JobSourceRecord] = []
    for index, (industry, title, city, url) in enumerate(rows, start=1):
        records.append(
            _record(
                external_id=f"market-baseline:{index:03d}",
                source="market_baseline",
                title=title,
                company=f"{industry}主流岗位",
                city=city,
                salary="面议",
                url=url,
                industry=industry,
                function=title,
                jd_text=f"{title} 是 {industry} 方向常见面试岗位，用于岗位理解、简历匹配和模拟面试训练；不代表实时招聘中的具体空缺。",
                metadata={
                    "source_type": "market_baseline",
                    "source_adapter": "market_baseline_catalog",
                    "public_access": True,
                    "login_required": False,
                    "live_posting": False,
                    "market_region": "CN",
                },
            )
        )
    return records


def fetch_third_party_search_jobs() -> list[JobSourceRecord]:
    if not settings.serpapi_api_key:
        return []
    response = httpx.get(
        "https://serpapi.com/search.json",
        params={"q": "site:jobs.bytedance.com OR site:careers.tencent.com 招聘 产品经理 北京", "api_key": settings.serpapi_api_key},
        timeout=20,
    )
    response.raise_for_status()
    records: list[JobSourceRecord] = []
    for index, item in enumerate(response.json().get("organic_results", [])[:20], start=1):
        title = _safe_text(item.get("title"))
        link = _safe_text(item.get("link"))
        if not title or not link:
            continue
        company = _company_from_url(link)
        records.append(
            JobSourceRecord(
                external_id=f"third-party-search:{index}:{_slug(link)}",
                source="third_party_search",
                title=title[:120],
                company=company,
                city=None,
                salary_range=None,
                duration=None,
                jd_text=_safe_text(item.get("snippet") or title),
                apply_url=link,
                metadata={"source_type": "third_party_search", "provider": "serpapi", "market_region": "CN"},
            )
        )
    return records


def fetch_liepin_mcp_jobs(
    *,
    client: Any | None = None,
    queries: str | None = None,
    limit_per_query: int | None = None,
    company: str | None = None,
) -> list[JobSourceRecord]:
    """Fetch jobs from Liepin's authorized MCP endpoint and normalize them."""
    effective_url = settings.liepin_mcp_url or LIEPIN_MCP_DEFAULT_URL
    if client is None:
        if not settings.liepin_mcp_token:
            return []
        client = LiepinMcpClient(
            url=effective_url,
            token=settings.liepin_mcp_token,
            tool_name=settings.liepin_mcp_tool_name,
            timeout_seconds=settings.liepin_mcp_timeout_seconds,
        )
    records: dict[str, JobSourceRecord] = {}
    for keyword, city in _parse_liepin_query_plan(queries or settings.liepin_mcp_queries):
        payload = client.search_jobs(keyword=keyword, city=city, limit=limit_per_query or settings.liepin_mcp_limit_per_query, company=company)
        _raise_liepin_business_error(payload)
        for record in parse_liepin_mcp_payload(payload, query_keyword=keyword, query_city=city, query_company=company):
            records[record.external_id] = record
    return list(records.values())


def parse_liepin_mcp_payload(
    payload: dict[str, Any] | list[Any],
    *,
    query_keyword: str | None = None,
    query_city: str | None = None,
    query_company: str | None = None,
) -> list[JobSourceRecord]:
    """Map Liepin MCP search results to the common job source record shape."""
    records: list[JobSourceRecord] = []
    for index, item in enumerate(_extract_liepin_items(payload), start=1):
        if not isinstance(item, dict):
            continue
        title = _first_text(item, "title", "job_title", "jobName", "positionName", "position", "name", "职位名称", "岗位名称")
        company = _first_text(item, "company", "companyName", "compName", "corpName", "enterpriseName", "公司名称", "企业名称")
        url = _https_url(_first_text(item, "apply_url", "applyUrl", "jobUrl", "jobDetailUrl", "detailUrl", "url", "link", "href", "职位链接"))
        if not title or not company or not url:
            continue
        job_id = _first_text(item, "job_id", "jobId", "id", "positionId", "position_id", "职位ID") or _slug(f"{company}-{title}-{url}")
        city = _first_text(item, "city", "workCity", "cityName", "location", "dq", "address", "工作城市") or query_city
        salary = _first_text(item, "salary", "salaryRange", "salaryText", "compensation", "薪资", "薪资范围")
        description = _first_text(item, "jd_text", "jd", "description", "jobDescription", "requirement", "summary", "岗位描述", "职位描述")
        jd_parts = [
            description,
            f"学历要求：{_first_text(item, 'education', 'eduLevel', '学历')}" if _first_text(item, "education", "eduLevel", "学历") else "",
            f"经验要求：{_first_text(item, 'workYears', 'workExperience', '经验')}" if _first_text(item, "workYears", "workExperience", "经验") else "",
            f"行业：{_first_text(item, 'industry', '行业')}" if _first_text(item, "industry", "行业") else "",
        ]
        jd_text = _clean_text("；".join(part for part in jd_parts if part) or f"{company} {title}，来自猎聘 MCP 授权岗位检索。")
        posted_at = _parse_datetime(_first_text(item, "posted_at", "publishTime", "updateTime", "createdAt", "发布时间"))
        records.append(
            JobSourceRecord(
                external_id=f"liepin-mcp:{job_id}",
                source="liepin_mcp",
                title=title[:160],
                company=company[:120],
                city=city[:80] if city else None,
                salary_range=salary[:120] if salary else None,
                duration=_first_text(item, "duration", "jobType", "employmentType", "工作性质") or None,
                jd_text=jd_text,
                apply_url=url,
                deadline=None,
                posted_at=posted_at,
                metadata={
                    "source_type": "mcp",
                    "source_adapter": "liepin_mcp",
                    "authorized_mcp": True,
                    "public_access": False,
                    "login_required": True,
                    "live_posting": True,
                    "market_region": "CN",
                    "query_keyword": query_keyword,
                    "query_city": query_city,
                    "query_company": query_company,
                    "raw_index": index,
                    "function": _infer_function(title),
                },
            )
        )
    return records


def _raise_liepin_business_error(payload: dict[str, Any] | list[Any]) -> None:
    """Surface Liepin MCP business errors instead of silently treating them as no results."""
    if not isinstance(payload, dict):
        return
    code = payload.get("code")
    if code in {None, 0, "0"}:
        return
    message = _safe_text(payload.get("msg") or payload.get("message"))
    data = payload.get("data")
    if not message and isinstance(data, dict):
        message = _safe_text(data.get("result") or data.get("message"))
    raise RuntimeError(f"Liepin MCP business error {code}: {message or 'unknown error'}")


def default_adapters() -> list[JobSourceAdapter]:
    adapters: list[JobSourceAdapter] = []
    if settings.enable_global_ats:
        for board in DEFAULT_ASHBY_BOARDS:
            adapters.append(JobSourceAdapter(name=f"ashby:{board}", source_type="ats", fetch=lambda board=board: fetch_ashby_jobs(board)))
        for board in DEFAULT_GREENHOUSE_BOARDS:
            adapters.append(JobSourceAdapter(name=f"greenhouse:{board}", source_type="ats", fetch=lambda board=board: fetch_greenhouse_jobs(board)))
        for board in DEFAULT_LEVER_BOARDS:
            adapters.append(JobSourceAdapter(name=f"lever:{board}", source_type="ats", fetch=lambda board=board: fetch_lever_jobs(board)))
    adapters.extend(
        [
            JobSourceAdapter(name="tencent_official", source_type="official_company", fetch=fetch_tencent_jobs),
            JobSourceAdapter(name="official_company_catalog", source_type="official_company", fetch=fetch_official_company_jobs),
            JobSourceAdapter(name="public_board", source_type="public_board", fetch=fetch_public_board_jobs),
            JobSourceAdapter(
                name="third_party_search",
                source_type="third_party_search",
                fetch=fetch_third_party_search_jobs,
                enabled=bool(settings.serpapi_api_key or settings.apify_token),
                disabled_reason="SERPAPI_API_KEY or APIFY_TOKEN is not configured.",
            ),
            JobSourceAdapter(
                name="liepin_mcp",
                source_type="mcp",
                fetch=fetch_liepin_mcp_jobs,
                enabled=bool(settings.enable_liepin_mcp and (settings.liepin_mcp_url or LIEPIN_MCP_DEFAULT_URL) and settings.liepin_mcp_token),
                disabled_reason=_liepin_mcp_disabled_reason(),
            ),
            JobSourceAdapter(name="market_baseline", source_type="market_baseline", fetch=fetch_market_baseline_jobs),
        ]
    )
    return adapters


def default_fetchers() -> list[FetchFn]:
    return [adapter.fetch for adapter in default_adapters() if adapter.enabled]


def default_source_statuses() -> dict[str, dict[str, Any]]:
    statuses: dict[str, dict[str, Any]] = {
        name: {"status": data["status"], "reason": data["reason"], "records": 0}
        for name, data in RESTRICTED_PLATFORM_STATUS.items()
    }
    if not settings.enable_global_ats:
        statuses["global_ats"] = {"status": "disabled", "reason": "ENABLE_GLOBAL_ATS is false; domestic public sources are preferred.", "records": 0}
    for adapter in default_adapters():
        statuses.setdefault(
            adapter.name.split(":", 1)[0],
            {
                "status": "enabled" if adapter.enabled else "disabled",
                "reason": adapter.disabled_reason,
                "records": 0,
            },
        )
    return statuses


def _liepin_mcp_disabled_reason() -> str | None:
    if not settings.enable_liepin_mcp:
        return "ENABLE_LIEPIN_MCP is false."
    if not settings.liepin_mcp_token:
        return "LIEPIN_MCP_TOKEN is not configured."
    if not (settings.liepin_mcp_url or LIEPIN_MCP_DEFAULT_URL):
        return "LIEPIN_MCP_URL is not configured."
    return None


def _parse_mcp_http_response(response: httpx.Response) -> dict[str, Any]:
    content_type = response.headers.get("content-type", "")
    if "text/event-stream" not in content_type:
        return response.json()
    last_payload: dict[str, Any] | None = None
    for line in response.text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line.removeprefix("data:").strip()
        if not data or data == "[DONE]":
            continue
        parsed = json.loads(data)
        if isinstance(parsed, dict):
            last_payload = parsed
    if last_payload is None:
        raise ValueError("Liepin MCP SSE response did not include JSON data.")
    return last_payload


def _extract_mcp_tool_payload(result: Any) -> dict[str, Any] | list[Any]:
    if not isinstance(result, dict):
        return result
    structured = result.get("structuredContent") or result.get("structured_content")
    if isinstance(structured, (dict, list)):
        return structured
    content = result.get("content")
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, (dict, list)):
                return parsed
    return result


def _select_liepin_search_tool(tools: list[dict[str, Any]]) -> dict[str, Any]:
    scored: list[tuple[int, dict[str, Any]]] = []
    for tool in tools:
        name = _safe_text(tool.get("name")).lower()
        description = _safe_text(tool.get("description")).lower()
        text = f"{name} {description}"
        score = 0
        for token in ["job", "position", "recruit", "search", "query", "职位", "岗位", "招聘", "猎聘"]:
            if token in text:
                score += 1
        scored.append((score, tool))
    scored.sort(key=lambda item: item[0], reverse=True)
    if scored and scored[0][0] > 0:
        return scored[0][1]
    raise ValueError("Liepin MCP did not expose a recognizable job search tool.")


def _build_liepin_tool_arguments(schema: dict[str, Any], *, keyword: str, city: str | None, limit: int, company: str | None = None) -> dict[str, Any]:
    properties = schema.get("properties") if isinstance(schema, dict) else None
    if not isinstance(properties, dict) or not properties:
        args: dict[str, Any] = {"keyword": keyword, "limit": limit}
        if company:
            args["company"] = company
        if city:
            args["city"] = city
        return args

    args = {}
    for name in properties:
        lower = name.lower()
        if any(token in lower for token in ["company", "comp", "corp", "enterprise"]) or any(token in name for token in ["公司", "企业"]):
            if company:
                args[name] = company
        elif any(token in lower for token in ["keyword", "query", "search", "jobname", "position", "q"]) or any(token in name for token in ["关键词", "职位", "岗位"]):
            args[name] = keyword
        elif "city" in lower or "location" in lower or lower == "address" or any(token in name for token in ["城市", "地点"]):
            if city:
                args[name] = city
        elif any(token in lower for token in ["limit", "pagesize", "page_size", "size", "count"]):
            args[name] = limit
        elif lower in {"page", "pageindex", "page_index"}:
            args[name] = 0

    required = schema.get("required") if isinstance(schema, dict) else None
    if isinstance(required, list):
        for name in required:
            if name in args:
                continue
            lower = str(name).lower()
            if any(token in lower for token in ["keyword", "query", "search", "position", "q"]):
                args[name] = keyword
            elif any(token in lower for token in ["company", "comp", "corp", "enterprise"]) and company:
                args[name] = company
            elif "city" in lower and city:
                args[name] = city
            elif any(token in lower for token in ["limit", "size", "count"]):
                args[name] = limit
    return args or {"keyword": keyword, "company": company, "city": city, "limit": limit}


def _parse_liepin_query_plan(value: str) -> list[tuple[str, str | None]]:
    pairs: list[tuple[str, str | None]] = []
    for raw in re.split(r"[;\n]+", value or ""):
        text = raw.strip()
        if not text:
            continue
        if "@" in text:
            keyword, city = text.split("@", 1)
            pairs.append((keyword.strip(), city.strip() or None))
        else:
            pairs.append((text, None))
    return pairs or [("产品经理", "北京")]


def _extract_liepin_items(payload: dict[str, Any] | list[Any]) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    direct_keys = ["jobs", "jobList", "positions", "items", "list", "records", "data"]
    for key in direct_keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = _extract_liepin_items(value)
            if nested:
                return nested
    for value in payload.values():
        if isinstance(value, dict):
            nested = _extract_liepin_items(value)
            if nested:
                return nested
    return []


def _first_text(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        if isinstance(value, dict):
            value = value.get("name") or value.get("text") or value.get("value")
        text = _safe_text(value)
        if text:
            return text
    return ""


def parse_ashby_payload(*, board: str, payload: dict[str, Any]) -> list[JobSourceRecord]:
    records: list[JobSourceRecord] = []
    for item in payload.get("jobs", []) or []:
        job_id = _safe_text(item.get("id") or item.get("jobId") or item.get("externalId"))
        title = _safe_text(item.get("title"))
        if not job_id or not title:
            continue
        compensation = item.get("compensation") or {}
        salary = compensation.get("compensationTierSummary") or compensation.get("summary") if isinstance(compensation, dict) else None
        records.append(
            JobSourceRecord(
                external_id=f"ashby:{board}:{job_id}",
                source="ashby",
                title=title,
                company=_company_from_board(board),
                city=_normalize_location(item.get("location") or item.get("locationName")),
                salary_range=_safe_text(salary) if salary else None,
                duration=None,
                jd_text=_clean_text(item.get("descriptionPlain") or item.get("descriptionHtml") or item.get("description") or ""),
                apply_url=_safe_text(item.get("jobUrl") or item.get("applyUrl") or item.get("url")) or None,
                deadline=None,
                posted_at=_parse_datetime(item.get("publishedAt") or item.get("createdAt")),
                metadata={"source_type": "ats", "board": board, "market_region": "Global"},
            )
        )
    return records


def parse_greenhouse_payload(*, board: str, payload: dict[str, Any]) -> list[JobSourceRecord]:
    records: list[JobSourceRecord] = []
    for item in payload.get("jobs", []) or []:
        job_id = _safe_text(item.get("id"))
        title = _safe_text(item.get("title"))
        if not job_id or not title:
            continue
        location = item.get("location") or {}
        records.append(
            JobSourceRecord(
                external_id=f"greenhouse:{board}:{job_id}",
                source="greenhouse",
                title=title,
                company=_company_from_board(board),
                city=_normalize_location(location.get("name") if isinstance(location, dict) else location),
                salary_range=None,
                duration=None,
                jd_text=_clean_text(item.get("content") or item.get("description") or ""),
                apply_url=_safe_text(item.get("absolute_url") or item.get("url")) or None,
                deadline=None,
                posted_at=_parse_datetime(item.get("updated_at")),
                metadata={"source_type": "ats", "board": board, "market_region": "Global"},
            )
        )
    return records


def parse_lever_payload(*, board: str, payload: list[dict[str, Any]]) -> list[JobSourceRecord]:
    records: list[JobSourceRecord] = []
    for item in payload or []:
        job_id = _safe_text(item.get("id"))
        title = _safe_text(item.get("text"))
        if not job_id or not title:
            continue
        categories = item.get("categories") or {}
        records.append(
            JobSourceRecord(
                external_id=f"lever:{board}:{job_id}",
                source="lever",
                title=title,
                company=_company_from_board(board),
                city=_normalize_location(categories.get("location") if isinstance(categories, dict) else None),
                salary_range=None,
                duration=None,
                jd_text=_clean_text(item.get("descriptionPlain") or item.get("description") or ""),
                apply_url=_safe_text(item.get("hostedUrl") or item.get("applyUrl")) or None,
                deadline=None,
                posted_at=_parse_datetime(item.get("createdAt")),
                metadata={"source_type": "ats", "board": board, "market_region": "Global"},
            )
        )
    return records


def _record(
    *,
    external_id: str,
    source: str,
    title: str,
    company: str,
    city: str,
    salary: str | None,
    url: str,
    industry: str,
    function: str,
    jd_text: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> JobSourceRecord:
    base_metadata = {
        "industry": industry,
        "function": function,
        "source_type": source,
        "market_region": "CN",
    }
    base_metadata.update(metadata or {})
    return JobSourceRecord(
        external_id=external_id,
        source=source,
        title=title,
        company=company,
        city=city,
        salary_range=salary,
        duration=None,
        jd_text=jd_text or f"{company} {title}，方向：{industry}/{function}。岗位信息来自公开招聘入口，用于求职搜索、匹配和面试训练。",
        apply_url=url,
        deadline=None,
        metadata=base_metadata,
    )


def _company_from_board(board: str) -> str:
    special = {"databricks": "Databricks", "airbnb": "Airbnb", "scaleai": "Scale AI"}
    return special.get(board, board.replace("-", " ").title())


def _company_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    mapping = {
        "bytedance": "字节跳动",
        "qq.com": "腾讯",
        "tencent": "腾讯",
        "alibaba": "阿里巴巴",
        "meituan": "美团",
        "jd.com": "京东",
        "baidu": "百度",
        "huawei": "华为",
    }
    for key, value in mapping.items():
        if key in host:
            return value
    return host.replace("www.", "") or "第三方搜索结果"


def _normalize_location(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("name") or value.get("location")
    text = _safe_text(value)
    return text or None


def _clean_text(value: Any) -> str:
    text = unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _https_url(value: str) -> str | None:
    if not value:
        return None
    return re.sub(r"^http://", "https://", value.strip())


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _parse_cn_date(value: Any) -> datetime | None:
    text = _safe_text(value)
    match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", text)
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    return datetime(year, month, day)


def _infer_function(title: str) -> str:
    text = title.lower()
    if any(token in text for token in ["产品", "product"]):
        return "产品"
    if any(token in text for token in ["后端", "开发", "工程", "engineer"]):
        return "工程技术"
    if any(token in text for token in ["数据", "data", "分析"]):
        return "数据"
    if any(token in text for token in ["运营", "operation"]):
        return "运营"
    if any(token in text for token in ["市场", "marketing"]):
        return "市场"
    return "综合"


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", value).strip("-").lower()
    return slug[:80] or "unknown"
