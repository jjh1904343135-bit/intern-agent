"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { EmptyState } from "@/components/empty-state";
import { JobCard, type JobCardItem } from "@/components/job-card";
import { PageShell } from "@/components/page-shell";
import { StatusPill } from "@/components/status-pill";
import { SurfaceCard } from "@/components/surface-card";
import { apiJson, apiRequest, type ApiEnvelope } from "@/lib/api";
import { clearTokens, isAuthenticated } from "@/lib/auth";

type JobsPayload = {
  total: number;
  jobs: JobCardItem[];
  source_kind?: string;
  fallback_notice?: string | null;
  query_expansions?: string[];
  source_status?: Record<string, { status: string; reason?: string | null; records?: number }>;
};

type ApplyPayload = {
  application_id: string;
  status: string;
};

type SavedJobFilters = {
  keyword: string;
  city: string;
  jobType: string;
  experience: string;
  limit: string;
};

const FILTER_STORAGE_KEY = "intern-agent:jobs:filters";
const defaultFilters: SavedJobFilters = {
  keyword: "产品经理",
  city: "",
  jobType: "",
  experience: "",
  limit: "30",
};

export default function JobsPage() {
  const [authenticated, setAuthenticated] = useState(false);
  const [jobs, setJobs] = useState<JobCardItem[]>([]);
  const [keyword, setKeyword] = useState(defaultFilters.keyword);
  const [city, setCity] = useState("");
  const [jobType, setJobType] = useState("");
  const [experience, setExperience] = useState("");
  const [limit, setLimit] = useState("30");
  const [preferMatch, setPreferMatch] = useState(false);
  const [filtersReady, setFiltersReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [discoveryNotice, setDiscoveryNotice] = useState("");

  useEffect(() => {
    const authed = isAuthenticated();
    const saved = readSavedFilters();
    setAuthenticated(authed);
    setPreferMatch(authed);
    setKeyword(saved.keyword);
    setCity(saved.city);
    setJobType(saved.jobType);
    setExperience(saved.experience);
    setLimit(saved.limit);
    setFiltersReady(true);
    void loadJobs({ nextKeyword: saved.keyword, nextCity: saved.city, nextLimit: saved.limit, nextPreferMatch: authed, nextAuthenticated: authed });
  }, []);

  useEffect(() => {
    if (!filtersReady) {
      return;
    }
    window.localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify({ keyword, city, jobType, experience, limit }));
  }, [city, experience, filtersReady, jobType, keyword, limit]);

  const sourceLine = useMemo(() => {
    const sources = Array.from(new Set(jobs.map((job) => job.source).filter(Boolean)));
    if (sources.length === 0) {
      return "等待岗位数据";
    }
    return sources.map((source) => source.toUpperCase()).join(" / ");
  }, [jobs]);

  const suggestions = useMemo(() => buildSearchSuggestions(keyword), [keyword]);
  const visibleJobs = useMemo(() => filterJobs(jobs, { jobType, experience }), [experience, jobType, jobs]);

  async function loadJobs({
    nextKeyword,
    nextCity,
    nextLimit,
    nextPreferMatch,
    nextAuthenticated = authenticated,
  }: {
    nextKeyword: string;
    nextCity?: string;
    nextLimit?: string;
    nextPreferMatch: boolean;
    nextAuthenticated?: boolean;
  }) {
    setLoading(true);
    setError("");
    setSuccess("");
    setDiscoveryNotice("");

    const query = new URLSearchParams();
    query.set("match_resume", String(nextPreferMatch));
    query.set("limit", String(Math.min(Math.max(Number(nextLimit || limit || 30) || 30, 1), 100)));
    if (nextKeyword.trim()) {
      query.set("keyword", nextKeyword.trim());
    }
    if ((nextCity ?? city).trim()) {
      query.set("city", (nextCity ?? city).trim());
    }

    try {
      const response = await apiRequest<ApiEnvelope<JobsPayload>>(`/api/v1/jobs/search?${query.toString()}`, {
        auth: nextAuthenticated,
      });
      setJobs(response.data.jobs);
      setDiscoveryNotice(response.data.fallback_notice || buildSourceNotice(response.data.source_status));
      setPreferMatch(nextPreferMatch);
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "岗位加载失败";
      if (nextAuthenticated || nextPreferMatch) {
        const tokenLooksInvalid = /token|auth|unauthorized|认证|登录|subject/i.test(message);
        if (tokenLooksInvalid) {
          clearTokens();
          setAuthenticated(false);
        }
        setError(
          message.includes("Default parsed resume is required")
            ? "还没有可用于匹配的默认简历，已先展示全部岗位。上传并解析简历后可看到匹配分。"
            : "登录状态不可用，已切换为访客岗位列表。",
        );
        try {
          const fallbackQuery = new URLSearchParams();
          fallbackQuery.set("match_resume", "false");
          fallbackQuery.set("limit", String(Math.min(Math.max(Number(nextLimit || limit || 30) || 30, 1), 100)));
          if (nextKeyword.trim()) {
            fallbackQuery.set("keyword", nextKeyword.trim());
          }
          if ((nextCity ?? city).trim()) {
            fallbackQuery.set("city", (nextCity ?? city).trim());
          }
          const fallback = await apiRequest<ApiEnvelope<JobsPayload>>(`/api/v1/jobs/search?${fallbackQuery.toString()}`, {
            auth: false,
          });
          setJobs(fallback.data.jobs);
          setDiscoveryNotice(fallback.data.fallback_notice || buildSourceNotice(fallback.data.source_status));
          setPreferMatch(false);
        } catch (fallbackError) {
          setJobs([]);
          setError(fallbackError instanceof Error ? fallbackError.message : "岗位加载失败");
        }
      } else {
        setJobs([]);
        setError(message);
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await loadJobs({ nextKeyword: keyword, nextCity: city, nextLimit: limit, nextPreferMatch: preferMatch });
  }

  async function useSuggestion(value: string) {
    setKeyword(value);
    await loadJobs({ nextKeyword: value, nextCity: city, nextLimit: limit, nextPreferMatch: preferMatch });
  }

  async function handleSave(jobId: string) {
    if (!authenticated) {
      setError("请先登录，再把岗位保存到投递清单。");
      return;
    }

    setError("");
    setSuccess("");
    try {
      const response = await apiJson<ApiEnvelope<ApplyPayload>>(`/api/v1/jobs/${jobId}/apply`, { cover_letter: null }, true);
      setSuccess(response.data.status === "saved" ? "已保存到投递清单，下一步去原站手动投递。" : "投递清单已更新。");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "保存失败");
    }
  }

  return (
    <PageShell>
      <SurfaceCard className="grid gap-6 lg:grid-cols-[0.78fr_1.22fr]">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.35em] text-blue-600">Jobs</p>
          <h1 className="mt-3 font-display text-4xl text-slate-950">岗位推荐</h1>
          <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-600">先浏览，再保存。登录并上传简历后会显示匹配理由。</p>
          <div className="mt-5 flex flex-wrap gap-2">
            <StatusPill tone={authenticated ? "success" : "neutral"}>{authenticated ? "可使用简历匹配" : "无需简历也可浏览"}</StatusPill>
            <StatusPill>{sourceLine}</StatusPill>
          </div>
        </div>

        <form className="grid content-end gap-4" onSubmit={handleSearch}>
          <div className="grid gap-3 sm:grid-cols-[1fr_120px_120px_120px_86px_auto]">
            <input
              className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-slate-900"
              onChange={(event) => setKeyword(event.target.value)}
              placeholder="搜索岗位、公司、城市或技能"
              value={keyword}
            />
            <input
              className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-slate-900"
              onChange={(event) => setCity(event.target.value)}
              placeholder="城市"
              value={city}
            />
            <select
              className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-slate-900"
              onChange={(event) => setJobType(event.target.value)}
              value={jobType}
            >
              <option value="">不限类型</option>
              <option value="intern">实习</option>
              <option value="full_time">正式</option>
            </select>
            <select
              className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-slate-900"
              onChange={(event) => setExperience(event.target.value)}
              value={experience}
            >
              <option value="">不限经验</option>
              <option value="intern">实习</option>
              <option value="entry">校招</option>
              <option value="senior">资深</option>
            </select>
            <input
              className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-slate-900"
              min={1}
              max={100}
              onChange={(event) => setLimit(event.target.value)}
              placeholder="数量"
              type="number"
              value={limit}
            />
            <button className="action-button justify-center px-6 py-3" disabled={loading} type="submit">
              {loading ? "搜索中..." : "搜索"}
            </button>
          </div>
          {suggestions.length ? (
            <div className="flex flex-wrap gap-2">
              {suggestions.map((item) => (
                <button className="rounded-full border border-blue-100 bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700" key={item} onClick={() => void useSuggestion(item)} type="button">
                  {item}
                </button>
              ))}
            </div>
          ) : null}
          <div className="flex flex-wrap gap-3">
            <button
              className={preferMatch ? "action-button" : "secondary-button"}
              disabled={!authenticated || loading}
              onClick={() => void loadJobs({ nextKeyword: keyword, nextCity: city, nextLimit: limit, nextPreferMatch: true })}
              type="button"
            >
              {authenticated ? "简历匹配" : "上传简历后匹配"}
            </button>
            <button className={!preferMatch ? "action-button" : "secondary-button"} onClick={() => void loadJobs({ nextKeyword: keyword, nextCity: city, nextLimit: limit, nextPreferMatch: false })} type="button">
              全部岗位
            </button>
            <Link className="secondary-button" href="/applications">
              投递清单
            </Link>
          </div>
        </form>
      </SurfaceCard>

      {error ? <p className="rounded-2xl border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-700">{error}</p> : null}
      {discoveryNotice ? <p className="rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-700">{discoveryNotice}</p> : null}
      {success ? <p className="rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{success}</p> : null}

      {visibleJobs.length === 0 && !loading ? (
        <SurfaceCard>
          <EmptyState
            actions={[{ href: "/resume/upload", label: "上传简历" }, { href: "/chat", label: "问 AI 怎么搜", tone: "secondary" }]}
            description="换一个关键词，或先执行真实岗位同步脚本后再刷新。"
            title="暂时没有岗位结果"
          />
        </SurfaceCard>
      ) : null}

      <section className="grid gap-4 xl:grid-cols-2">
        {visibleJobs.map((job) => (
          <JobCard authenticated={authenticated} job={job} key={job.job_id || job.id} onSave={handleSave} />
        ))}
      </section>
    </PageShell>
  );
}

function readSavedFilters(): SavedJobFilters {
  if (typeof window === "undefined") {
    return defaultFilters;
  }
  try {
    return { ...defaultFilters, ...(JSON.parse(window.localStorage.getItem(FILTER_STORAGE_KEY) || "{}") as Partial<SavedJobFilters>) };
  } catch {
    return defaultFilters;
  }
}

function buildSearchSuggestions(value: string) {
  const normalized = value.trim().toLowerCase();
  if (!normalized) {
    return ["产品经理实习", "数据分析实习", "后端开发实习", "国企管培生"];
  }
  if (normalized.includes("产品") || normalized.includes("product")) {
    return ["产品经理实习", "AIGC 产品", "数据产品", "远程实习"];
  }
  if (normalized.includes("后端") || normalized.includes("backend")) {
    return ["Java 后端", "Go 后端", "平台后端", "后端实习"];
  }
  if (normalized.includes("数据") || normalized.includes("data")) {
    return ["数据分析实习", "商业分析", "数据产品", "BI 分析"];
  }
  return [];
}

function filterJobs(jobs: JobCardItem[], filters: { jobType: string; experience: string }) {
  return jobs.filter((job) => {
    const label = job.job_type_label ?? "";
    const matchesType =
      !filters.jobType ||
      job.job_type === filters.jobType ||
      (filters.jobType === "intern" && label.includes("实习")) ||
      (filters.jobType === "full_time" && label.includes("正式"));
    if (!matchesType) {
      return false;
    }
    const matchesExperience = !filters.experience || job.experience === filters.experience || (filters.experience === "intern" && label.includes("实习"));
    if (!matchesExperience) {
      return false;
    }
    return true;
  });
}

function buildSourceNotice(sourceStatus?: JobsPayload["source_status"]) {
  if (!sourceStatus) {
    return "";
  }
  const disabledSearch = sourceStatus.third_party_search?.status === "disabled";
  const liepinMcpReady = ["ok", "enabled"].includes(sourceStatus.liepin_mcp?.status ?? "");
  if (liepinMcpReady) {
    return "猎聘 MCP 已接入，已使用授权岗位源补充实时岗位。";
  }
  const blockedPlatforms = ["boss", "liepin", "zhaopin", "51job", "lagou"].filter((name) => {
    return sourceStatus[name]?.status === "blocked";
  });
  if (!disabledSearch && blockedPlatforms.length === 0) {
    return "";
  }
  const blockedText = blockedPlatforms.length > 0 ? blockedPlatforms.map(platformDisplayName).join("、") : "受限招聘平台";
  return `已优先使用公开岗位源；${blockedText} 等登录、验证码或风控页面不会被绕过。`;
}

function platformDisplayName(name: string) {
  const labels: Record<string, string> = {
    boss: "BOSS",
    liepin: "猎聘网页",
    zhaopin: "智联",
    "51job": "前程无忧",
    lagou: "拉勾",
  };
  return labels[name] ?? name;
}
