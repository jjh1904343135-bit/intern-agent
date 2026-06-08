"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { PageShell } from "@/components/page-shell";
import { ResumeFlowSvg } from "@/components/qingcheng-visuals";
import { ResumeProgressTimeline, type ResumeProgress } from "@/components/resume-progress-timeline";
import { SectionIntro } from "@/components/section-intro";
import { StatusPill } from "@/components/status-pill";
import { SurfaceCard } from "@/components/surface-card";
import { apiRequest, uploadWithProgress, type ApiEnvelope } from "@/lib/api";
import { formatStatusLabel } from "@/lib/format";
import { isAuthenticated } from "@/lib/auth";

type UploadResponse = {
  resume_id: string;
  parse_status: string;
  estimated_seconds: number;
  progress: ResumeProgress;
};

type ResumeStatusPayload = {
  resume_id: string;
  parse_status: string;
  progress: ResumeProgress;
};

export default function ResumeUploadPage() {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const timerRef = useRef<number | null>(null);
  const [authenticated, setAuthenticated] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(0);
  const [resumeId, setResumeId] = useState("");
  const [status, setStatus] = useState("");
  const [pipelineProgress, setPipelineProgress] = useState<ResumeProgress | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setAuthenticated(isAuthenticated());
    return () => {
      if (timerRef.current) {
        window.clearInterval(timerRef.current);
      }
    };
  }, []);

  async function pollStatus(id: string) {
    const result = await apiRequest<ApiEnvelope<ResumeStatusPayload>>(`/api/v1/resume/${id}/status`, { auth: true });
    setStatus(result.data.parse_status);
    setPipelineProgress(result.data.progress);
    if (["done", "failed"].includes(result.data.parse_status)) {
      if (timerRef.current) {
        window.clearInterval(timerRef.current);
      }
      if (result.data.parse_status === "done") {
        window.location.assign(`/resume/${id}/status`);
      }
    }
  }

  async function handleUpload() {
    if (!authenticated) {
      setError("请先登录，再上传并解析简历。");
      return;
    }

    if (!file) {
      setError("请先选择一份 PDF 或 DOCX 简历。");
      return;
    }

    setLoading(true);
    setError("");
    setProgress(0);

    try {
      const response = await uploadWithProgress<ApiEnvelope<UploadResponse>>("/api/v1/resume/upload", file, setProgress);
      setResumeId(response.data.resume_id);
      setStatus(response.data.parse_status);
      setPipelineProgress(response.data.progress);
      timerRef.current = window.setInterval(() => {
        void pollStatus(response.data.resume_id);
      }, 2000);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "上传失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  }

  function handlePickedFile(nextFile: File | null) {
    setFile(nextFile);
    setError("");
    setProgress(0);
    if (!nextFile) {
      setResumeId("");
      setStatus("");
      setPipelineProgress(null);
    }
  }

  return (
    <PageShell>
      <SurfaceCard className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="space-y-6">
          <SectionIntro
            eyebrow="Resume Upload"
            title="上传简历"
            description="支持 PDF / DOCX。完成后直接查看评分和下一步建议。"
            actions={
              <>
                <button className="action-button" onClick={handleUpload} type="button" disabled={loading}>
                  {loading ? "正在上传..." : "开始上传"}
                </button>
                <Link className="secondary-button" href="/jobs">
                  先去看岗位
                </Link>
              </>
            }
          />

          <div
            className={`grid min-h-[260px] place-items-center rounded-[32px] border-2 border-dashed px-6 py-8 text-center transition ${
              dragActive ? "border-blue-500 bg-blue-50" : "border-slate-300 bg-slate-50"
            }`}
            onDragEnter={(event) => {
              event.preventDefault();
              setDragActive(true);
            }}
            onDragLeave={(event) => {
              event.preventDefault();
              setDragActive(false);
            }}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              setDragActive(false);
              handlePickedFile(event.dataTransfer.files?.[0] ?? null);
            }}
          >
            <div className="max-w-xl space-y-4">
              <div className="mx-auto inline-flex h-16 w-16 items-center justify-center rounded-full bg-blue-600 text-2xl font-semibold text-white shadow-[0_16px_30px_rgba(37,99,235,0.25)]">
                CV
              </div>
              <div>
                <h2 className="text-2xl font-semibold text-slate-950">拖拽简历到这里</h2>
                <p className="mt-3 text-sm leading-7 text-slate-600">也可以点击选择文件。解析完成后自动进入结果页。</p>
              </div>
              <button className="secondary-button" onClick={() => inputRef.current?.click()} type="button">
                选择文件
              </button>
              <input
                ref={inputRef}
                accept=".pdf,.docx"
                className="hidden"
                onChange={(event) => handlePickedFile(event.target.files?.[0] ?? null)}
                type="file"
              />
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-[1fr_auto] lg:items-center">
            <div className="space-y-3 rounded-[28px] border border-slate-200 bg-white px-5 py-5">
              <div className="flex flex-wrap items-center gap-3">
                <StatusPill>{status ? formatStatusLabel(status) : authenticated ? "待上传" : "未登录"}</StatusPill>
                {file ? <StatusPill tone="success">已选择文件</StatusPill> : null}
              </div>
              <p className="text-base font-medium text-slate-900">{file ? file.name : "还没有选择简历文件"}</p>
              <p className="text-sm text-slate-500">{file ? `文件大小 ${(file.size / 1024 / 1024).toFixed(2)} MB` : "建议准备一份与目标岗位相关度高的简历版本。"}</p>
              <div className="h-3 overflow-hidden rounded-full bg-slate-100">
                <div className="h-full rounded-full bg-blue-600 transition-all" style={{ width: `${progress}%` }} />
              </div>
              <p className="text-sm text-slate-500">上传进度 {progress}%</p>
              {error ? <p className="rounded-2xl border border-rose-100 bg-rose-50 px-4 py-3 text-sm text-rose-600">{error}</p> : null}
            </div>

            {resumeId ? (
              <Link className="secondary-button" href={`/resume/${resumeId}/status`}>
                直接查看状态页
              </Link>
            ) : null}
          </div>

          <ResumeProgressTimeline progress={pipelineProgress} />
        </div>

        <div className="grid gap-6">
          <SurfaceCard className="border-none bg-blue-600 text-white shadow-[0_24px_70px_rgba(37,99,235,0.2)]">
            <p className="text-xs font-semibold uppercase tracking-[0.35em] text-blue-200">Workflow</p>
            <h2 className="mt-3 text-2xl font-semibold">上传后下一步</h2>
            <div className="mt-6 overflow-hidden rounded-[30px] bg-white/10 p-2">
              <ResumeFlowSvg />
            </div>
          </SurfaceCard>

          <SurfaceCard>
            <p className="text-xs font-semibold uppercase tracking-[0.35em] text-blue-600">Quick Access</p>
            <h2 className="mt-3 text-2xl font-semibold text-slate-950">先看看也可以</h2>
            <div className="mt-6 grid gap-3 text-sm">
              <Link className="secondary-button w-fit" href="/jobs">
                浏览岗位列表
              </Link>
              <Link className="secondary-button w-fit" href="/applications">
                查看投递中心
              </Link>
              <Link className="secondary-button w-fit" href="/chat">
                让 AI 帮我梳理简历方向
              </Link>
            </div>
          </SurfaceCard>
        </div>
      </SurfaceCard>
    </PageShell>
  );
}

