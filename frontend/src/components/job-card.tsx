import Link from "next/link";

import { StatusPill } from "@/components/status-pill";
import { formatDate, truncateText } from "@/lib/format";

export type JobCardItem = {
  id: string;
  job_id?: string;
  title: string;
  raw_title?: string;
  canonical_title?: string;
  company: string;
  city: string | null;
  salary: string | null;
  duration: string | null;
  deadline: string | null;
  source: string;
  apply_url: string | null;
  url?: string | null;
  jd_text: string | null;
  summary?: string | null;
  experience?: string | null;
  job_type?: string | null;
  job_type_label?: string | null;
  market_region?: string | null;
  skills?: string[];
  popularity_score?: number;
  match_score?: number;
  function?: string;
  specialization?: string | null;
  recommendation_score?: number;
  explanation?: string;
  matched_skills?: string[];
  missing_skills?: string[];
  application_priority?: string;
  posted_at?: string | null;
  last_seen_at?: string | null;
  is_active?: boolean | null;
  score_dimensions?: Array<{
    dimension: string;
    score: number;
    weight: number;
    evidence?: string[];
    problems?: string[];
    suggestions?: string[];
    confidence?: number;
  }>;
};

type JobCardProps = {
  job: JobCardItem;
  authenticated: boolean;
  onSave: (jobId: string) => void | Promise<void>;
};

export function JobCard({ job, authenticated, onSave }: JobCardProps) {
  const jobId = job.job_id || job.id;
  const displayTitle = job.canonical_title || job.title;
  const rawTitle = job.raw_title || job.title;
  const description = job.summary || job.jd_text || "暂无职位描述";
  const applyUrl = job.apply_url || job.url;
  const hasRecommendation = Boolean(job.explanation || job.matched_skills?.length || job.missing_skills?.length || typeof job.recommendation_score === "number");

  return (
    <article className="flex h-full flex-col justify-between rounded-[28px] border border-slate-200 bg-white p-5 shadow-[0_16px_44px_rgba(15,23,42,0.06)] transition hover:-translate-y-0.5 hover:border-blue-200 hover:shadow-[0_22px_56px_rgba(37,99,235,0.1)]">
      <div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill>{job.company}</StatusPill>
            <StatusPill tone="neutral">来源 {job.source}</StatusPill>
            {typeof job.popularity_score === "number" ? <StatusPill tone="success">热度 {job.popularity_score}</StatusPill> : null}
            {typeof job.recommendation_score === "number" ? <StatusPill tone="success">推荐 {Math.round(job.recommendation_score * 100)}</StatusPill> : null}
            {job.application_priority ? <StatusPill tone="neutral">优先级 {job.application_priority}</StatusPill> : null}
            {job.experience ? <StatusPill tone="neutral">{job.experience}</StatusPill> : null}
            {job.job_type_label ? <StatusPill tone="neutral">{job.job_type_label}</StatusPill> : null}
            {job.market_region === "CN" ? <StatusPill tone="success">中国优先</StatusPill> : null}
          </div>
          {typeof job.match_score === "number" ? (
            <div className="grid h-16 w-16 place-items-center rounded-2xl bg-blue-600 text-center text-white shadow-[0_18px_35px_rgba(37,99,235,0.24)]">
              <span className="text-2xl font-semibold leading-none">{job.match_score}</span>
              <span className="text-[10px] leading-none text-blue-100">MATCH</span>
            </div>
          ) : null}
        </div>

        <h2 className="mt-5 text-2xl font-semibold tracking-tight text-slate-950">{displayTitle}</h2>
        {rawTitle !== displayTitle ? <p className="mt-2 text-xs font-medium text-slate-500">原始标题：{rawTitle}</p> : null}
        {job.function || job.specialization ? <p className="mt-2 text-xs text-slate-500">{[job.function, job.specialization].filter(Boolean).join(" · ")}</p> : null}
        <p className="mt-3 text-sm text-slate-500">{job.city || "城市待定"} · {job.duration || "周期待定"} · 截止 {formatDate(job.deadline)}</p>
        <p className="mt-2 text-sm font-semibold text-slate-900">{job.salary || "薪资待沟通"}</p>
        {job.skills && job.skills.length > 0 ? (
          <div className="mt-4 flex flex-wrap gap-2">
            {job.skills.slice(0, 6).map((skill) => (
              <span className="rounded-full border border-blue-100 bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700" key={skill}>
                {skill}
              </span>
            ))}
          </div>
        ) : null}
        {hasRecommendation ? (
          <div className="mt-4 rounded-[22px] border border-blue-100 bg-blue-50/80 px-4 py-4">
            <p className="text-sm font-semibold text-blue-950">推荐理由</p>
            {job.explanation ? <p className="mt-2 text-sm leading-6 text-blue-900">{job.explanation}</p> : null}
            <div className="mt-3 grid gap-2 text-xs text-slate-600 sm:grid-cols-2">
              <div>
                <p className="font-semibold text-slate-900">匹配技能</p>
                <p className="mt-1">{job.matched_skills?.length ? job.matched_skills.join("、") : "登录并上传简历后生成"}</p>
              </div>
              <div>
                <p className="font-semibold text-slate-900">缺失技能</p>
                <p className="mt-1 text-amber-700">{job.missing_skills?.length ? job.missing_skills.join("、") : "暂无明显缺口"}</p>
              </div>
            </div>
            {job.matched_skills?.length ? <p className="mt-3 text-xs text-slate-500">匹配：{job.matched_skills.join("、")}</p> : null}
            {job.missing_skills?.length ? <p className="mt-1 text-xs text-amber-700">缺口：{job.missing_skills.join("、")}</p> : null}
            {job.score_dimensions?.length ? (
              <div className="mt-4 rounded-[18px] bg-white/80 px-3 py-3">
                <p className="text-xs font-semibold text-slate-900">证据链</p>
                <div className="mt-2 grid gap-2">
                  {job.score_dimensions.slice(0, 2).map((dimension) => (
                    <div className="text-xs leading-5 text-slate-600" key={dimension.dimension}>
                      <p className="font-semibold text-slate-800">
                        {dimension.dimension} {Math.round(dimension.score * 100)}
                      </p>
                      {dimension.evidence?.[0] ? <p className="mt-0.5">{dimension.evidence[0]}</p> : null}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        ) : null}
        {job.last_seen_at ? <p className="mt-2 text-xs text-slate-400">{job.is_active === false ? "疑似失效" : "最近更新"}：{formatDate(job.last_seen_at)}</p> : null}
        <p className="mt-5 text-sm leading-7 text-slate-600">{truncateText(description, 150)}</p>
      </div>

      <div className="mt-6 flex flex-wrap gap-3">
        <Link className="secondary-button" href={`/jobs/${jobId}`}>
          查看详情
        </Link>
        <button className="action-button" onClick={() => void onSave(jobId)} type="button">
          {authenticated ? "保存到投递清单" : "登录后保存"}
        </button>
        {applyUrl ? (
          <a className="secondary-button" href={applyUrl} rel="noreferrer" target="_blank">
            去原站投递
          </a>
        ) : null}
        <Link className="secondary-button" href={`/interview/start?jobId=${jobId}`}>
          模拟面试
        </Link>
      </div>
    </article>
  );
}
