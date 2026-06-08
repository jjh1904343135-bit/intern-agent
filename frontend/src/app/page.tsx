"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { MetricCard } from "@/components/metric-card";
import { PageShell } from "@/components/page-shell";
import { ProductPreviewSvg } from "@/components/qingcheng-visuals";
import { StatusPill } from "@/components/status-pill";
import { SurfaceCard } from "@/components/surface-card";
import { apiRequest, type ApiEnvelope } from "@/lib/api";
import { isAuthenticated } from "@/lib/auth";
import { formatStatusLabel, truncateText } from "@/lib/format";

type HealthPayload = {
  status: string;
  app: string;
  env: string;
  provider: string;
};

type DashboardSummary = {
  overview: {
    resume_count: number;
    applications_total: number;
    active_applications: number;
    interview_sessions: number;
    chat_sessions: number;
  };
  resume: {
    resume_id: string;
    file_name: string;
    parse_status: string;
    updated_at: string | null;
    score: {
      overall_score: number;
      label: string;
      summary: string;
      highlights: string[];
      risks: string[];
      next_actions: string[];
      source: string;
      model: string;
      status: string;
    } | null;
  } | null;
  applications: {
    total: number;
    active_count: number;
    status_breakdown: Record<string, number>;
    recent: Array<{
      application_id: string;
      status: string;
      applied_at: string | null;
      status_updated_at: string | null;
    }>;
  };
  interview: {
    total: number;
    latest: {
      session_id: string;
      mode: string;
      overall_score: number | null;
    } | null;
  };
  chat: {
    total: number;
    latest_preview: {
      session_id: string;
      preview: string;
    } | null;
  };
  next_actions: string[];
  recommended_actions?: Array<{
    kind: string;
    title: string;
    description: string;
    href: string;
    priority: number;
  }>;
};

const visitorCards = [
  { title: "简历评分", hint: "上传后看到分数、亮点和风险", href: "/resume/upload" },
  { title: "国内岗位", hint: "浏览公开岗位和主流职业方向", href: "/jobs" },
  { title: "投递清单", hint: "保存岗位，跟进真实进度", href: "/applications" },
  { title: "AI 助手", hint: "把问题变成下一步动作", href: "/chat" },
];

export default function HomePage() {
  const [authenticated, setAuthenticated] = useState(false);
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [dashboard, setDashboard] = useState<DashboardSummary | null>(null);
  const [healthError, setHealthError] = useState("");
  const [dashboardError, setDashboardError] = useState("");

  useEffect(() => {
    const authed = isAuthenticated();
    setAuthenticated(authed);

    apiRequest<HealthPayload>("/health")
      .then(setHealth)
      .catch((error: Error) => setHealthError(error.message));

    if (authed) {
      apiRequest<ApiEnvelope<DashboardSummary>>("/api/v1/dashboard/summary", { auth: true })
        .then((payload) => setDashboard(payload.data))
        .catch((error: Error) => setDashboardError(error.message));
    }
  }, []);

  const providerLine = useMemo(() => {
    if (health) {
      return `${health.provider} · ${health.env}`;
    }
    return healthError || "检查中";
  }, [health, healthError]);

  return (
    <PageShell>
      <SurfaceCard className="grid gap-6 lg:grid-cols-[1.05fr_0.95fr]">
        <div>
          <div className="flex flex-wrap gap-2">
            <StatusPill tone={health?.status === "ok" ? "success" : "neutral"}>{health?.status === "ok" ? "系统在线" : "连接中"}</StatusPill>
            <StatusPill>{providerLine}</StatusPill>
          </div>
          <h1 className="mt-5 font-display text-4xl text-slate-950 lg:text-5xl">
            {authenticated ? "今天推进哪一步？" : "青程 AI，让求职下一步更清楚"}
          </h1>
          <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-600">
            {authenticated ? "看简历、找岗位、跟投递、练面试。首页只告诉你现在该做什么。" : "上传简历，搜索岗位，保存投递，再用 AI 准备面试。"}
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            {authenticated ? (
              <>
                <Link className="action-button" href="/jobs">找岗位</Link>
                <Link className="secondary-button" href="/resume/upload">更新简历</Link>
                <Link className="secondary-button" href="/chat">问 AI</Link>
              </>
            ) : (
              <>
                <Link className="action-button" href="/auth/login">登录</Link>
                <Link className="secondary-button" href="/auth/register">注册</Link>
              </>
            )}
          </div>
        </div>

        <div className="overflow-hidden rounded-[32px] border border-blue-100 bg-blue-50 p-2 shadow-inner shadow-blue-100/70">
          <ProductPreviewSvg />
        </div>
      </SurfaceCard>

      {authenticated ? (
        dashboard ? (
          <>
            <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <MetricCard accent="primary" hint={dashboard.resume?.score?.label ?? "等待评审"} label="简历分" value={dashboard.resume?.score?.overall_score ?? "--"} />
              <MetricCard hint="清单中的岗位" label="投递" value={dashboard.overview.applications_total} />
              <MetricCard hint="需要继续跟进" label="待跟进" value={dashboard.overview.active_applications} />
              <MetricCard hint="已创建会话" label="AI/面试" value={dashboard.overview.chat_sessions + dashboard.overview.interview_sessions} />
            </section>

            <section className="grid gap-6 xl:grid-cols-[1.08fr_0.92fr]">
              <SurfaceCard>
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.35em] text-blue-600">Resume</p>
                    <h2 className="mt-3 text-2xl font-semibold text-slate-950">{dashboard.resume?.file_name ?? "还没有默认简历"}</h2>
                    <p className="mt-4 text-sm leading-7 text-slate-600">
                      {dashboard.resume?.score?.summary ?? "上传一份简历后，这里会显示 Gemma4 评分摘要。"}
                    </p>
                  </div>
                  {dashboard.resume ? <StatusPill>{formatStatusLabel(dashboard.resume.parse_status)}</StatusPill> : null}
                </div>

                {dashboard.resume?.score ? (
                  <div className="mt-6 grid gap-4 md:grid-cols-2">
                    <div className="rounded-[28px] border border-emerald-100 bg-emerald-50 px-5 py-5">
                      <p className="text-sm font-semibold text-emerald-800">亮点</p>
                      <div className="mt-3 grid gap-2 text-sm leading-6 text-emerald-900">
                        {dashboard.resume.score.highlights.slice(0, 3).map((item) => <p key={item}>{item}</p>)}
                      </div>
                    </div>
                    <div className="rounded-[28px] border border-rose-100 bg-rose-50 px-5 py-5">
                      <p className="text-sm font-semibold text-rose-800">风险</p>
                      <div className="mt-3 grid gap-2 text-sm leading-6 text-rose-900">
                        {dashboard.resume.score.risks.slice(0, 3).map((item) => <p key={item}>{item}</p>)}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="mt-6">
                    <EmptyState actions={[{ href: "/resume/upload", label: "上传简历" }]} description="评分完成后会自动出现在这里。" title="暂无评分" />
                  </div>
                )}
              </SurfaceCard>

              <div className="grid gap-6">
                <SurfaceCard className="border-none bg-slate-950 text-white shadow-none">
                  <p className="text-xs font-semibold uppercase tracking-[0.35em] text-blue-200">Next</p>
                  <h2 className="mt-3 text-2xl font-semibold">下一步行动</h2>
                  <div className="mt-5 grid gap-3 text-sm leading-6 text-slate-200">
                    {(dashboard.recommended_actions?.length
                      ? dashboard.recommended_actions
                      : dashboard.next_actions.map((item, index) => ({
                          kind: `legacy-${index}`,
                          title: item,
                          description: item,
                          href: "/jobs",
                          priority: 0,
                        }))
                    ).slice(0, 3).map((item) => (
                      <Link key={`${item.kind}-${item.href}`} className="rounded-[24px] border border-white/10 bg-white/5 px-4 py-4 transition hover:bg-white/10" href={item.href}>
                        <span className="block font-medium text-white">{item.title}</span>
                        <span className="mt-1 block text-xs leading-5 text-slate-300">{item.description}</span>
                      </Link>
                    ))}
                  </div>
                  <div className="mt-6 flex flex-wrap gap-3">
                    <Link className="action-button" href="/jobs">去岗位页</Link>
                    <Link className="secondary-button border-white/20 text-white hover:border-white hover:text-white" href="/chat">问 AI</Link>
                  </div>
                </SurfaceCard>

                <SurfaceCard>
                  <p className="text-xs font-semibold uppercase tracking-[0.35em] text-blue-600">Recent</p>
                  <h2 className="mt-3 text-2xl font-semibold text-slate-950">最近动态</h2>
                  <div className="mt-5 grid gap-3 text-sm leading-6 text-slate-600">
                    <p>投递：{Object.entries(dashboard.applications.status_breakdown).map(([key, value]) => `${formatStatusLabel(key)} ${value}`).join(" / ") || "暂无"}</p>
                    <p>面试：{dashboard.interview.latest ? `${dashboard.interview.latest.mode} · ${dashboard.interview.latest.overall_score ?? "未评分"}` : "暂无"}</p>
                    <p>对话：{dashboard.chat.latest_preview ? truncateText(dashboard.chat.latest_preview.preview, 80) : "暂无"}</p>
                  </div>
                </SurfaceCard>
              </div>
            </section>
          </>
        ) : (
          <SurfaceCard>
            <EmptyState
              actions={[{ href: "/resume/upload", label: "上传简历" }, { href: "/auth/login", label: "重新登录", tone: "secondary" }]}
              description={dashboardError || "正在等待仪表盘数据。"}
              title="仪表盘暂不可用"
            />
          </SurfaceCard>
        )
      ) : (
        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {visitorCards.map((card) => (
            <Link key={card.href} className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-[0_20px_55px_rgba(15,23,42,0.07)] transition hover:-translate-y-0.5 hover:border-blue-200 hover:bg-blue-50" href={card.href}>
              <h2 className="text-2xl font-semibold text-slate-950">{card.title}</h2>
              <p className="mt-3 text-sm leading-6 text-slate-600">{card.hint}</p>
            </Link>
          ))}
        </section>
      )}
    </PageShell>
  );
}
