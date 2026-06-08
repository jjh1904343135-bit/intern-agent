"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import type { JobCardItem } from "@/components/job-card";
import { JobDecisionPanel } from "@/components/job-decision-panel";
import { PageShell } from "@/components/page-shell";
import { StatusPill } from "@/components/status-pill";
import { SurfaceCard } from "@/components/surface-card";
import { apiJson, apiRequest, type ApiEnvelope } from "@/lib/api";

 type JobDetail = JobCardItem & {
  interview_context?: {
    title?: string;
    company?: string;
    city?: string | null;
    salary?: string | null;
    job_type_label?: string;
    skills?: string[];
    jd_summary?: string;
  };
};

type ApplyPayload = {
  application_id: string;
  status: string;
};

type StartInterviewPayload = {
  session_id: string;
  reused?: boolean;
};

export default function JobDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const jobId = params.id;
  const [job, setJob] = useState<JobDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [starting, setStarting] = useState<"reuse" | "new" | "">("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const loadJob = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await apiRequest<ApiEnvelope<JobDetail>>(`/api/v1/jobs/${jobId}`);
      setJob(response.data);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "岗位详情加载失败");
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    void loadJob();
  }, [loadJob]);

  async function handleSave() {
    if (!job) {
      return;
    }
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const response = await apiJson<ApiEnvelope<ApplyPayload>>(`/api/v1/jobs/${job.id}/apply`, { cover_letter: null }, true);
      setMessage(response.data.status === "saved" ? "已保存到投递清单。" : "投递清单已更新。");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "保存失败，请先登录。");
    } finally {
      setSaving(false);
    }
  }

  async function handleStartInterview(forceNew: boolean) {
    if (!job) {
      return;
    }
    setStarting(forceNew ? "new" : "reuse");
    setError("");
    setMessage("");
    try {
      const response = await apiJson<ApiEnvelope<StartInterviewPayload>>(
        "/api/v1/interview/session/start",
        { job_id: job.id, mode: "standard", force_new: forceNew },
        true,
      );
      router.push(`/interview/${response.data.session_id}`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "开始面试失败，请先登录并上传已解析简历。");
    } finally {
      setStarting("");
    }
  }

  if (loading) {
    return (
      <PageShell>
        <SurfaceCard>正在加载岗位...</SurfaceCard>
      </PageShell>
    );
  }

  if (!job) {
    return (
      <PageShell>
        <SurfaceCard>
          <p className="text-sm text-rose-600">{error || "岗位不存在"}</p>
          <Link className="mt-5 inline-flex text-sm font-medium text-blue-600" href="/jobs">
            返回岗位
          </Link>
        </SurfaceCard>
      </PageShell>
    );
  }

  const skills = job.interview_context?.skills?.length ? job.interview_context.skills : job.skills || [];
  const applyUrl = job.apply_url || job.url;

  return (
    <PageShell className="max-w-5xl">
      <SurfaceCard>
        <div className="flex flex-wrap items-center gap-2">
          <StatusPill>{job.company}</StatusPill>
          {job.job_type_label ? <StatusPill>{job.job_type_label}</StatusPill> : null}
          {job.market_region === "CN" ? <StatusPill tone="success">中国岗位</StatusPill> : null}
          <StatusPill tone="neutral">来源 {job.source}</StatusPill>
        </div>

        <h1 className="mt-5 text-3xl font-semibold tracking-tight text-slate-950 sm:text-4xl">{job.title}</h1>
        <p className="mt-4 text-base text-slate-600">
          {job.company} · {job.city || "地点待定"} · {job.salary || "薪资待沟通"}
        </p>

        <div className="mt-7 flex flex-wrap gap-3">
          <button className="action-button" disabled={saving} onClick={() => void handleSave()} type="button">
            {saving ? "保存中..." : "保存到投递清单"}
          </button>
          <button className="secondary-button" disabled={Boolean(starting)} onClick={() => void handleStartInterview(false)} type="button">
            {starting === "reuse" ? "打开中..." : "模拟面试"}
          </button>
          <button className="secondary-button" disabled={Boolean(starting)} onClick={() => void handleStartInterview(true)} type="button">
            {starting === "new" ? "创建中..." : "新开一轮面试"}
          </button>
          {applyUrl ? (
            <a className="secondary-button" href={applyUrl} rel="noreferrer" target="_blank">
              去原站投递
            </a>
          ) : null}
        </div>

        {message ? <p className="mt-5 rounded-2xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{message}</p> : null}
        {error ? <p className="mt-5 rounded-2xl bg-amber-50 px-4 py-3 text-sm text-amber-700">{error}</p> : null}
      </SurfaceCard>

      <JobDecisionPanel job={job} />

      <section className="grid gap-5 lg:grid-cols-[0.7fr_1.3fr]">
        <SurfaceCard>
          <h2 className="text-lg font-semibold text-slate-950">岗位信息</h2>
          <dl className="mt-5 grid gap-4 text-sm">
            <div>
              <dt className="text-slate-400">地点</dt>
              <dd className="mt-1 text-slate-900">{job.city || "未标明"}</dd>
            </div>
            <div>
              <dt className="text-slate-400">薪资</dt>
              <dd className="mt-1 text-slate-900">{job.salary || "未标明"}</dd>
            </div>
            <div>
              <dt className="text-slate-400">类型</dt>
              <dd className="mt-1 text-slate-900">{job.job_type_label || "未标明"}</dd>
            </div>
            <div>
              <dt className="text-slate-400">方向</dt>
              <dd className="mt-1 text-slate-900">{[job.function, job.specialization].filter(Boolean).join(" · ") || "未归类"}</dd>
            </div>
          </dl>

          {skills.length ? (
            <div className="mt-6 flex flex-wrap gap-2">
              {skills.slice(0, 10).map((skill) => (
                <span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700" key={skill}>
                  {skill}
                </span>
              ))}
            </div>
          ) : null}
        </SurfaceCard>

        <SurfaceCard>
          <h2 className="text-lg font-semibold text-slate-950">职位描述</h2>
          <p className="mt-5 whitespace-pre-wrap text-sm leading-7 text-slate-700">{job.jd_text || job.summary || "暂无职位描述"}</p>
        </SurfaceCard>
      </section>
    </PageShell>
  );
}
