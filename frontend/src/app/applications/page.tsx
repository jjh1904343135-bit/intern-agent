"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { MetricCard } from "@/components/metric-card";
import { PageShell } from "@/components/page-shell";
import { StatusPill } from "@/components/status-pill";
import { SurfaceCard } from "@/components/surface-card";
import { apiJson, apiRequest, type ApiEnvelope } from "@/lib/api";
import { isAuthenticated } from "@/lib/auth";
import { formatDate, formatStatusLabel } from "@/lib/format";

type ApplicationItem = {
  application_id: string;
  job_id: string;
  resume_id: string;
  status: string;
  timeline: string[];
  status_flow?: string[];
  tracking_notes?: ApplicationTrackingNotes;
  status_updated_at: string | null;
  applied_at: string | null;
  job: {
    title: string | null;
    company: string | null;
    city: string | null;
    apply_url: string | null;
    source?: string | null;
  };
};

type ApplicationTrackingNotes = {
  platform?: string;
  applied_date?: string;
  hr_contact?: string;
  feedback_result?: string;
};

type ApplicationsPayload = {
  total: number;
  items: ApplicationItem[];
};

const activeStatuses = new Set(["saved", "opened", "applied_manual", "waiting_feedback", "interviewing", "interview_invited", "offer_received"]);

function getRecommendation(status: string) {
  switch (status) {
    case "saved":
      return "先打开原站，确认岗位仍在招聘，再决定是否投递。";
    case "opened":
      return "你已经打开过原站。如果完成投递，记得回来点击确认。";
    case "applied_manual":
      return "如果已提交，下一步标记为等待反馈，并补充投递平台和日期。";
    case "waiting_feedback":
      return "设置跟进提醒，记录 HR 联系方式或平台反馈。";
    case "interviewing":
      return "进入面试阶段，建议马上按该岗位开一轮模拟面试。";
    case "closed":
      return "这条机会已结束，可以保留复盘备注，继续搜索相近岗位。";
    case "interview_invited":
      return "立即进入模拟面试，围绕岗位要求补齐 STAR 叙事。";
    case "offer_received":
      return "进入选择与谈薪阶段，记录关键比较维度。";
    default:
      return "回到岗位页继续补充新的目标岗位。";
  }
}

export default function ApplicationsPage() {
  const [authenticated, setAuthenticated] = useState(false);
  const [items, setItems] = useState<ApplicationItem[]>([]);
  const [noteDrafts, setNoteDrafts] = useState<Record<string, ApplicationTrackingNotes>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const authed = isAuthenticated();
    setAuthenticated(authed);
    if (authed) {
      void loadApplications();
    }
  }, []);

  async function loadApplications() {
    setLoading(true);
    setError("");
    try {
      const response = await apiRequest<ApiEnvelope<ApplicationsPayload>>("/api/v1/applications", { auth: true });
      setItems(response.data.items);
      setNoteDrafts(Object.fromEntries(response.data.items.map((item) => [item.application_id, item.tracking_notes ?? {}])));
    } catch (requestError) {
      setItems([]);
      setNoteDrafts({});
      setError(requestError instanceof Error ? requestError.message : "投递记录加载失败");
    } finally {
      setLoading(false);
    }
  }

  async function markOpened(item: ApplicationItem) {
    if (item.status === "saved") {
      await apiJson<ApiEnvelope<ApplicationItem>>(`/api/v1/applications/${item.application_id}/mark-opened`, {}, true);
      await loadApplications();
    }
    if (item.job.apply_url) {
      window.open(item.job.apply_url, "_blank", "noopener,noreferrer");
    }
  }

  async function markApplied(item: ApplicationItem) {
    setError("");
    try {
      await apiJson<ApiEnvelope<ApplicationItem>>(`/api/v1/applications/${item.application_id}/mark-applied`, {}, true);
      await loadApplications();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "状态更新失败");
    }
  }

  async function markStatus(item: ApplicationItem, endpoint: "mark-waiting-feedback" | "mark-interviewing" | "mark-closed") {
    setError("");
    try {
      await apiJson<ApiEnvelope<ApplicationItem>>(`/api/v1/applications/${item.application_id}/${endpoint}`, {}, true);
      await loadApplications();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "状态更新失败");
    }
  }

  function updateDraft(applicationId: string, key: keyof ApplicationTrackingNotes, value: string) {
    setNoteDrafts((current) => ({
      ...current,
      [applicationId]: {
        ...(current[applicationId] ?? {}),
        [key]: value,
      },
    }));
  }

  async function saveNotes(item: ApplicationItem) {
    setError("");
    try {
      await apiRequest<ApiEnvelope<ApplicationItem>>(`/api/v1/applications/${item.application_id}/notes`, {
        method: "PATCH",
        body: JSON.stringify(noteDrafts[item.application_id] ?? {}),
        auth: true,
      });
      await loadApplications();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "备注保存失败");
    }
  }

  const savedCount = useMemo(() => items.filter((item) => item.status === "saved").length, [items]);
  const openedCount = useMemo(() => items.filter((item) => item.status === "opened").length, [items]);
  const appliedCount = useMemo(() => items.filter((item) => item.status === "applied_manual").length, [items]);
  const focusItem = useMemo(() => items.find((item) => activeStatuses.has(item.status)) ?? items[0] ?? null, [items]);

  if (!authenticated) {
    return (
      <PageShell>
        <SurfaceCard>
          <EmptyState
            actions={[{ href: "/auth/login", label: "登录查看" }, { href: "/jobs", label: "先浏览岗位", tone: "secondary" }]}
            description="投递清单只记录登录后的真实岗位动作：保存、打开原站、手动确认投递。"
            title="登录后管理投递"
          />
        </SurfaceCard>
      </PageShell>
    );
  }

  return (
    <PageShell>
      <SurfaceCard className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.35em] text-blue-600">Applications</p>
          <h1 className="mt-3 font-display text-4xl text-slate-950">投递清单</h1>
          <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-600">保存岗位、打开原站、确认投递和记录反馈。</p>
        </div>
        <div className="flex flex-wrap gap-3">
          <button className="action-button" onClick={() => void loadApplications()} type="button">
            刷新
          </button>
          <Link className="secondary-button" href="/jobs">
            继续找岗位
          </Link>
        </div>
      </SurfaceCard>

      {error ? <p className="rounded-2xl border border-rose-100 bg-rose-50 px-4 py-3 text-sm text-rose-600">{error}</p> : null}

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard accent="primary" hint="清单里的目标岗位" label="总数" value={items.length} />
        <MetricCard hint="需要去原站确认" label="已保存" value={savedCount} />
        <MetricCard hint="已访问原站链接" label="已打开" value={openedCount} />
        <MetricCard hint="你手动确认完成" label="已投递" value={appliedCount} />
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="grid gap-4">
          {loading ? <SurfaceCard><p className="text-sm text-slate-500">正在读取投递清单...</p></SurfaceCard> : null}

          {!loading && items.length === 0 ? (
            <SurfaceCard>
              <EmptyState
                actions={[{ href: "/jobs", label: "保存第一个岗位" }, { href: "/chat", label: "让 AI 帮我定策略", tone: "secondary" }]}
                description="先到岗位页保存真实岗位，投递清单才会形成可跟进的工作流。"
                title="还没有保存岗位"
              />
            </SurfaceCard>
          ) : null}

          {items.map((item) => (
            <SurfaceCard key={item.application_id} className="flex h-full flex-col justify-between">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <StatusPill>{item.job.company ?? "未知公司"}</StatusPill>
                  {item.job.source ? <StatusPill>来源 {item.job.source}</StatusPill> : null}
                  <StatusPill tone={activeStatuses.has(item.status) ? "success" : "neutral"}>{formatStatusLabel(item.status)}</StatusPill>
                </div>
                <h2 className="mt-5 font-display text-3xl text-slate-950">{item.job.title ?? "未知岗位"}</h2>
                <p className="mt-2 text-sm text-slate-500">{item.job.city ?? "城市待定"} · 保存时间 {formatDate(item.applied_at)}</p>
                <p className="mt-4 text-sm leading-7 text-slate-600">{getRecommendation(item.status)}</p>
                <div className="mt-5 flex flex-wrap gap-2 text-sm">
                  {(item.status_flow ?? item.timeline).map((step) => {
                    const completed = item.timeline.includes(step);
                    return (
                    <span key={`${item.application_id}-${step}`} className={`rounded-full px-3 py-1 ${step === item.status ? "bg-blue-600 text-white" : completed ? "bg-blue-50 text-blue-700" : "border border-slate-200 text-slate-400"}`}>
                      {formatStatusLabel(step)}
                    </span>
                    );
                  })}
                </div>
                <p className="mt-4 text-xs text-slate-400">更新于 {formatDate(item.status_updated_at)}</p>

                <div className="mt-5 grid gap-3 rounded-[24px] border border-slate-100 bg-slate-50 p-4">
                  <p className="text-sm font-medium text-slate-700">跟进备注</p>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <input className="rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm" onChange={(event) => updateDraft(item.application_id, "platform", event.target.value)} placeholder="投递平台" value={noteDrafts[item.application_id]?.platform ?? ""} />
                    <input className="rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm" onChange={(event) => updateDraft(item.application_id, "applied_date", event.target.value)} placeholder="投递日期" value={noteDrafts[item.application_id]?.applied_date ?? ""} />
                    <input className="rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm" onChange={(event) => updateDraft(item.application_id, "hr_contact", event.target.value)} placeholder="HR 联系方式" value={noteDrafts[item.application_id]?.hr_contact ?? ""} />
                    <input className="rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm" onChange={(event) => updateDraft(item.application_id, "feedback_result", event.target.value)} placeholder="反馈结果" value={noteDrafts[item.application_id]?.feedback_result ?? ""} />
                  </div>
                  <button className="w-fit rounded-full border border-slate-200 bg-white px-4 py-2 text-xs font-medium text-slate-700 transition hover:border-blue-200 hover:text-blue-700" onClick={() => void saveNotes(item)} type="button">
                    保存备注
                  </button>
                </div>
              </div>

              <div className="mt-6 flex flex-wrap gap-3">
                {item.job.apply_url ? (
                  <button className="action-button" onClick={() => void markOpened(item)} type="button">
                    去原站投递
                  </button>
                ) : null}
                <button className="secondary-button" onClick={() => void markApplied(item)} type="button">
                  我已手动投递
                </button>
                <button className="secondary-button" onClick={() => void markStatus(item, "mark-waiting-feedback")} type="button">
                  等待反馈
                </button>
                <button className="secondary-button" onClick={() => void markStatus(item, "mark-interviewing")} type="button">
                  面试中
                </button>
                <Link className="secondary-button" href={`/interview/start?jobId=${item.job_id}`}>
                  模拟面试
                </Link>
                <button className="secondary-button" onClick={() => void markStatus(item, "mark-closed")} type="button">
                  已结束
                </button>
              </div>
            </SurfaceCard>
          ))}
        </div>

        <div className="grid gap-6">
          <SurfaceCard className="border-none bg-slate-950 text-white shadow-none">
            <p className="text-xs font-semibold uppercase tracking-[0.35em] text-blue-200">Today</p>
            <h2 className="mt-3 text-2xl font-semibold">下一步只做一件事</h2>
            <p className="mt-5 text-sm leading-7 text-slate-200">{focusItem ? getRecommendation(focusItem.status) : "先保存一个真实岗位，再开始投递节奏。"}</p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link className="action-button" href="/chat">
                让 AI 拆跟进动作
              </Link>
              <Link className="secondary-button border-white/20 text-white hover:border-white hover:text-white" href="/resume/upload">
                更新简历
              </Link>
            </div>
          </SurfaceCard>

          <SurfaceCard>
            <p className="text-xs font-semibold uppercase tracking-[0.35em] text-blue-600">Reminder</p>
            <h2 className="mt-3 text-2xl font-semibold text-slate-950">投递边界</h2>
            <p className="mt-4 text-sm leading-7 text-slate-600">青程 AI 负责记录和提醒；最终投递仍在招聘原站完成。</p>
          </SurfaceCard>
        </div>
      </section>
    </PageShell>
  );
}
