"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { PageShell } from "@/components/page-shell";
import { ResumeProgressTimeline, type ResumeProgress } from "@/components/resume-progress-timeline";
import { ResumeScoreCard, type ResumeScore } from "@/components/resume-score-card";
import { StatusPill } from "@/components/status-pill";
import { SurfaceCard } from "@/components/surface-card";
import { apiRequest, type ApiEnvelope } from "@/lib/api";
import { formatStatusLabel } from "@/lib/format";

type ResumeStatusPayload = {
  resume_id: string;
  parse_status: string;
  file_name: string;
  parsed_content: {
    summary?: string;
    skills?: string[];
  } | null;
  parse_error: string | null;
  score: ResumeScore | null;
  progress: ResumeProgress;
};

export default function ResumeStatusPage() {
  const params = useParams<{ id: string }>();
  const timerRef = useRef<number | null>(null);
  const [payload, setPayload] = useState<ResumeStatusPayload | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    async function fetchStatus() {
      try {
        const response = await apiRequest<ApiEnvelope<ResumeStatusPayload>>(`/api/v1/resume/${params.id}/status`, { auth: true });
        setPayload(response.data);
        if (["done", "failed"].includes(response.data.parse_status) && timerRef.current) {
          window.clearInterval(timerRef.current);
        }
      } catch (requestError) {
        setError(requestError instanceof Error ? requestError.message : "状态查询失败");
      }
    }

    void fetchStatus();
    timerRef.current = window.setInterval(() => {
      void fetchStatus();
    }, 2000);

    return () => {
      if (timerRef.current) {
        window.clearInterval(timerRef.current);
      }
    };
  }, [params.id]);

  if (!payload && !error) {
    return (
      <PageShell>
        <SurfaceCard>
          <div className="flex items-center gap-3 text-sm text-slate-500">
            <StatusPill>解析中</StatusPill>
            正在读取简历评分报告...
          </div>
        </SurfaceCard>
      </PageShell>
    );
  }

  if (!payload) {
    return (
      <PageShell>
        <SurfaceCard>
          <EmptyState
            actions={[{ href: "/resume/upload", label: "重新上传" }, { href: "/", label: "回到工作台", tone: "secondary" }]}
            description={error || "稍后再试，或回到上传页重新提交。"}
            title="无法读取简历状态"
          />
        </SurfaceCard>
      </PageShell>
    );
  }

  return (
    <PageShell>
      <ResumeScoreCard
        fileName={payload.file_name}
        parseError={payload.parse_error}
        parseStatus={payload.parse_status}
        score={payload.score}
        skills={payload.parsed_content?.skills ?? []}
        summary={payload.parsed_content?.summary}
      />

      <ResumeProgressTimeline progress={payload.progress} />

      {payload.parse_status !== "done" ? (
        <SurfaceCard>
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="text-sm font-semibold text-slate-900">当前状态：{formatStatusLabel(payload.parse_status)}</p>
              <p className="mt-2 text-sm leading-7 text-slate-600">
                正在处理文件。页面会自动刷新，完成后会展示评分报告。
              </p>
            </div>
            <Link className="secondary-button w-fit" href="/resume/upload">
              返回上传页
            </Link>
          </div>
        </SurfaceCard>
      ) : (
        <SurfaceCard>
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="text-sm font-semibold text-slate-900">评分已完成</p>
              <p className="mt-2 text-sm leading-7 text-slate-600">下一步可以看推荐岗位、让 AI 拆风险点，或按岗位练一轮面试。</p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Link className="action-button" href="/jobs">
                看推荐岗位
              </Link>
              <Link className="secondary-button" href="/chat">
                让 AI 拆风险点
              </Link>
              <Link className="secondary-button" href="/interview/start">
                开始模拟面试
              </Link>
            </div>
          </div>
        </SurfaceCard>
      )}

      {error ? <p className="rounded-2xl border border-rose-100 bg-rose-50 px-4 py-3 text-sm text-rose-600">{error}</p> : null}
    </PageShell>
  );
}
