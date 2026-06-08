"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import { EmptyState } from "@/components/empty-state";
import { PageShell } from "@/components/page-shell";
import { SessionSidebar, type SidebarSession } from "@/components/session-sidebar";
import { apiJson, apiRequest, type ApiEnvelope } from "@/lib/api";

type JobItem = {
  id: string;
  title: string;
  company: string;
  city: string | null;
  salary?: string | null;
  job_type_label?: string | null;
  source?: string | null;
};

type JobsPayload = {
  jobs: JobItem[];
};

type DashboardPayload = {
  resume: null | {
    resume_id: string;
    file_name: string;
    parse_status: string;
    score?: { overall_score?: number } | null;
  };
};

type InterviewSessionSummary = {
  session_id: string;
  job_title: string;
  company?: string | null;
  resume_file_name?: string | null;
  status: string;
  round_index: number;
  max_rounds: number;
  preview?: string;
  summary?: string;
  last_question?: string;
  completion?: string;
};

type InterviewSessionListPayload = {
  total: number;
  sessions: InterviewSessionSummary[];
};

type StartInterviewPayload = {
  session_id: string;
  mode: string;
  job_id: string;
  resume_id: string;
  reused?: boolean;
  messages: Array<{ role: string; content: string }>;
};

const modes = [
  { value: "standard", label: "标准" },
  { value: "pressure", label: "压力" },
  { value: "case", label: "案例" },
  { value: "negotiation", label: "沟通" },
] as const;

function toSidebarSession(session: InterviewSessionSummary): SidebarSession {
  return {
    id: session.session_id,
    title: session.job_title || "模拟面试",
    subtitle: `${session.status} · ${session.completion ?? `${session.round_index}/${session.max_rounds}`}`,
    preview: session.resume_file_name ? `基于 ${session.resume_file_name}` : session.preview,
    summary: session.summary,
    lastQuestion: session.last_question,
    completion: session.completion,
  };
}

export default function InterviewStartPage() {
  const router = useRouter();
  const [preferredJobId, setPreferredJobId] = useState<string | null>(null);
  const [jobs, setJobs] = useState<JobItem[]>([]);
  const [sessions, setSessions] = useState<InterviewSessionSummary[]>([]);
  const [resume, setResume] = useState<DashboardPayload["resume"]>(null);
  const [jobId, setJobId] = useState("");
  const [mode, setMode] = useState<(typeof modes)[number]["value"]>("standard");
  const [forceNew, setForceNew] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setPreferredJobId(params.get("jobId"));
    setForceNew(params.get("forceNew") === "1" || params.get("forceNew") === "true");
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [jobsResponse, dashboardResponse, sessionsResponse] = await Promise.all([
        apiRequest<ApiEnvelope<JobsPayload>>("/api/v1/jobs/search?match_resume=false", { auth: true }),
        apiRequest<ApiEnvelope<DashboardPayload>>("/api/v1/dashboard/summary", { auth: true }),
        apiRequest<ApiEnvelope<InterviewSessionListPayload>>("/api/v1/interview/sessions", { auth: true }),
      ]);
      setJobs(jobsResponse.data.jobs);
      setResume(dashboardResponse.data.resume);
      setSessions(sessionsResponse.data.sessions);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "面试入口加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  useEffect(() => {
    if (!jobs.length) {
      return;
    }
    if (preferredJobId && jobs.some((job) => job.id === preferredJobId)) {
      setJobId(preferredJobId);
      return;
    }
    if (!jobId) {
      setJobId(jobs[0].id);
    }
  }, [jobs, preferredJobId, jobId]);

  const selectedJob = useMemo(() => jobs.find((job) => job.id === jobId) ?? null, [jobs, jobId]);
  const canStart = Boolean(resume?.resume_id && resume.parse_status === "done" && jobId);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!resume?.resume_id || resume.parse_status !== "done") {
      setError("先上传并解析完成一份简历，再开始模拟面试。");
      return;
    }
    if (!jobId) {
      setError("请先选择一个目标岗位。");
      return;
    }

    setSubmitting(true);
    setError("");
    try {
      const response = await apiJson<ApiEnvelope<StartInterviewPayload>>(
        "/api/v1/interview/session/start",
        { job_id: jobId, mode, resume_id: resume.resume_id, force_new: forceNew },
        true,
      );
      router.push(`/interview/${response.data.session_id}`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "创建面试会话失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <PageShell className="max-w-none gap-0 px-0 py-0">
      <div className="flex min-h-[calc(100vh-80px)] w-full bg-slate-50">
        <SessionSidebar
          activeSessionId={null}
          createLabel="新面试"
          emptyText={loading ? "正在读取面试..." : "暂无面试会话"}
          onCreate={() => undefined}
          onSelect={(sessionId) => router.push(`/interview/${sessionId}`)}
          sessions={sessions.map(toSidebarSession)}
          title="面试会话"
        />

        <div className="mx-auto flex w-full max-w-3xl flex-col px-4 py-8">
          <header className="mb-8 text-center">
            <h1 className="text-xl font-semibold text-slate-950">开始模拟面试</h1>
            <p className="mt-2 text-sm text-slate-500">选择岗位，青程 AI 会结合默认简历提问。</p>
          </header>

          {error ? <div className="mb-4 rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-600">{error}</div> : null}

          {!loading && (!resume || resume.parse_status !== "done") ? (
            <div className="rounded-[28px] border border-slate-200 bg-white p-8 shadow-sm">
              <EmptyState
                actions={[{ href: "/resume/upload", label: "上传简历" }]}
                description="面试会根据简历追问。请先上传并等待解析完成。"
                title="需要一份已解析简历"
              />
            </div>
          ) : null}

          {!loading && resume?.parse_status === "done" ? (
            <form className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm" onSubmit={handleSubmit}>
              <div className="mb-5 rounded-2xl bg-blue-50 px-4 py-3 text-sm text-blue-800">
                当前简历：{resume.file_name}{typeof resume.score?.overall_score === "number" ? ` · ${resume.score.overall_score} 分` : ""}
              </div>

              <label className="grid gap-2">
                <span className="text-sm font-medium text-slate-700">目标岗位</span>
                <select
                  className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-slate-900"
                  disabled={loading || jobs.length === 0}
                  onChange={(event) => setJobId(event.target.value)}
                  value={jobId}
                >
                  {jobs.map((job) => (
                    <option key={job.id} value={job.id}>
                      {job.title} · {job.company}{job.city ? ` · ${job.city}` : ""}{job.salary ? ` · ${job.salary}` : ""}
                    </option>
                  ))}
                </select>
              </label>

              <div className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-4">
                {modes.map((item) => (
                  <button
                    key={item.value}
                    className={`rounded-2xl border px-4 py-3 text-sm font-medium transition ${mode === item.value ? "border-blue-200 bg-blue-50 text-blue-800" : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"}`}
                    onClick={() => setMode(item.value)}
                    type="button"
                  >
                    {item.label}
                  </button>
                ))}
              </div>

              <label className="mt-5 flex items-start gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
                <input
                  checked={forceNew}
                  className="mt-1 h-4 w-4 rounded border-slate-300 text-blue-600"
                  onChange={(event) => setForceNew(event.target.checked)}
                  type="checkbox"
                />
                <span>
                  新开一轮面试
                  <span className="block text-xs text-slate-400">关闭时会继续打开这个岗位已有的最近一次面试。</span>
                </span>
              </label>

              {selectedJob ? (
                <p className="mt-5 text-sm text-slate-500">
                  本轮面试：{selectedJob.title} · {selectedJob.company}
                  {selectedJob.city ? ` · ${selectedJob.city}` : ""}
                  {selectedJob.salary ? ` · ${selectedJob.salary}` : ""}
                  {selectedJob.job_type_label ? ` · ${selectedJob.job_type_label}` : ""}
                </p>
              ) : null}

              <button className="mt-6 w-full rounded-full bg-slate-900 px-5 py-3 text-sm font-medium text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40" disabled={submitting || !canStart} type="submit">
                {submitting ? "正在打开..." : forceNew ? "新开一轮面试" : "继续/开始面试"}
              </button>
            </form>
          ) : null}

          <Link className="mt-5 text-center text-sm font-medium text-blue-600" href="/jobs">
            先去岗位页看看
          </Link>
        </div>
      </div>
    </PageShell>
  );
}
