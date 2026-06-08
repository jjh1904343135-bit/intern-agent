"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { PageShell } from "@/components/page-shell";
import { SectionIntro } from "@/components/section-intro";
import { StatusPill } from "@/components/status-pill";
import { SurfaceCard } from "@/components/surface-card";
import { apiRequest, type ApiEnvelope } from "@/lib/api";

type InterviewReportPayload = {
  session_id: string;
  mode: string;
  overall_score: number;
  dimensions: Record<string, number>;
  strengths: string[];
  improvements: string[];
  summary: string;
  agent_summary?: {
    pass_probability?: string;
    strongest_dimension?: string;
    weakest_dimension?: string;
    risk_points?: string[];
    improvement_suggestions?: string[];
  };
};

export default function InterviewReportPage() {
  const params = useParams<{ id: string }>();
  const sessionId = params.id;

  const [report, setReport] = useState<InterviewReportPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadReport() {
      setLoading(true);
      setError("");
      try {
        const response = await apiRequest<ApiEnvelope<InterviewReportPayload>>(`/api/v1/interview/session/${sessionId}/report`, { auth: true });
        setReport(response.data);
      } catch (requestError) {
        setError(requestError instanceof Error ? requestError.message : "报告加载失败");
      } finally {
        setLoading(false);
      }
    }

    void loadReport();
  }, [sessionId]);

  return (
    <PageShell>
      <SurfaceCard>
        <SectionIntro
          eyebrow="Interview Report"
          title="让每场模拟面试有一个能回看、能复盘的结论页"
          description="报告页的职责不是只给一个分数，而是把维度分、优势、改进项和一句话总结整理成可继续执行的结论。"
          actions={
            <>
              <Link className="secondary-button" href={`/interview/${sessionId}`}>
                回到会话
              </Link>
              <Link className="secondary-button" href="/interview/start">
                开始新会话
              </Link>
            </>
          }
        />
        {error ? <p className="mt-6 rounded-2xl border border-rose-100 bg-rose-50 px-4 py-3 text-sm text-rose-600">{error}</p> : null}
      </SurfaceCard>

      {loading ? (
        <SurfaceCard>
          <p className="text-sm text-slate-500">正在生成报告...</p>
        </SurfaceCard>
      ) : null}

      {!loading && !report ? (
        <SurfaceCard>
          <EmptyState
            actions={[
              { href: `/interview/${sessionId}`, label: "回到会话" },
              { href: "/interview/start", label: "重新开始", tone: "secondary" },
            ]}
            description="如果当前还没有可用报告，可以先回到会话页继续答题，再回来刷新结果。"
            title="这场面试还没有可展示的报告"
          />
        </SurfaceCard>
      ) : null}

      {report ? (
        <>
          <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <SurfaceCard className="border-none bg-slate-950 text-white shadow-[0_24px_60px_rgba(15,23,42,0.22)]">
              <p className="text-xs font-semibold uppercase tracking-[0.35em] text-blue-200">Overall Score</p>
              <p className="mt-4 text-6xl font-semibold">{report.overall_score}</p>
              <p className="mt-3 text-sm text-slate-300">通过概率：{report.agent_summary?.pass_probability ?? "待补充"}</p>
            </SurfaceCard>
            {Object.entries(report.dimensions).map(([key, value]) => (
              <SurfaceCard key={key}>
                <p className="text-xs font-semibold uppercase tracking-[0.3em] text-blue-600">{key}</p>
                <p className="mt-4 text-4xl font-semibold text-slate-950">{value}</p>
                <p className="mt-3 text-sm text-slate-500">维度表现</p>
              </SurfaceCard>
            ))}
          </section>

          <section className="grid gap-6 xl:grid-cols-[1.08fr_0.92fr]">
            <SurfaceCard>
              <div className="flex flex-wrap items-center gap-3">
                <StatusPill tone="success">总结</StatusPill>
                <StatusPill>{report.mode}</StatusPill>
              </div>
              <p className="mt-6 whitespace-pre-wrap text-sm leading-7 text-slate-700">{report.summary}</p>
              {report.agent_summary ? (
                <div className="mt-5 grid gap-3 rounded-[24px] bg-slate-50 px-4 py-4 text-sm text-slate-600 sm:grid-cols-2">
                  <p>最强项：{report.agent_summary.strongest_dimension ?? "待观察"}</p>
                  <p>短板：{report.agent_summary.weakest_dimension ?? "待观察"}</p>
                </div>
              ) : null}
            </SurfaceCard>

            <div className="grid gap-6">
              <SurfaceCard>
                <p className="text-xs font-semibold uppercase tracking-[0.35em] text-blue-600">Strengths</p>
                <h2 className="mt-3 font-display text-3xl text-slate-950">当前优势</h2>
                <div className="mt-6 flex flex-wrap gap-2">
                  {report.strengths.map((item) => (
                    <span key={item} className="rounded-full bg-blue-600 px-4 py-2 text-sm font-medium text-white">
                      {item}
                    </span>
                  ))}
                </div>
              </SurfaceCard>

              <SurfaceCard>
                <p className="text-xs font-semibold uppercase tracking-[0.35em] text-blue-600">Next Practice</p>
                <h2 className="mt-3 font-display text-3xl text-slate-950">下次练什么</h2>
                <div className="mt-6 flex flex-wrap gap-2">
                  {(report.agent_summary?.improvement_suggestions?.length ? report.agent_summary.improvement_suggestions : report.improvements).map((item) => (
                    <span key={item} className="rounded-full bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700">
                      {item}
                    </span>
                  ))}
                </div>
              </SurfaceCard>

              <SurfaceCard>
                <p className="text-xs font-semibold uppercase tracking-[0.35em] text-blue-600">Risks</p>
                <h2 className="mt-3 font-display text-3xl text-slate-950">高频追问风险</h2>
                <div className="mt-6 grid gap-2 text-sm leading-6 text-slate-600">
                  {(report.agent_summary?.risk_points?.length ? report.agent_summary.risk_points : ["继续准备可量化项目证据。"]).map((item) => (
                    <p key={item}>{item}</p>
                  ))}
                </div>
              </SurfaceCard>
            </div>
          </section>
        </>
      ) : null}
    </PageShell>
  );
}
