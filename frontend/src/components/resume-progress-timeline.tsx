export type ResumeProgressStage = {
  key: string;
  label: string;
  status: "done" | "current" | "pending" | "failed";
};

export type ResumeProgress = {
  current_stage: string;
  percent: number;
  label: string;
  stages: ResumeProgressStage[];
  failure_reason?: { code: string; message: string; detail?: string } | null;
};

type ResumeProgressTimelineProps = {
  progress?: ResumeProgress | null;
};

function fallbackProgress(): ResumeProgress {
  return {
    current_stage: "uploaded",
    percent: 0,
    label: "等待上传",
    stages: [
      { key: "uploaded", label: "上传成功", status: "pending" },
      { key: "extracting_text", label: "正在提取文本", status: "pending" },
      { key: "structuring", label: "正在结构化解析", status: "pending" },
      { key: "scoring", label: "正在评分", status: "pending" },
      { key: "completed", label: "完成", status: "pending" },
    ],
    failure_reason: null,
  };
}

function dotClass(status: ResumeProgressStage["status"]) {
  if (status === "done") {
    return "bg-blue-600 text-white";
  }
  if (status === "current") {
    return "bg-white text-blue-700 ring-4 ring-blue-100";
  }
  if (status === "failed") {
    return "bg-rose-600 text-white";
  }
  return "bg-slate-100 text-slate-400";
}

export function ResumeProgressTimeline({ progress }: ResumeProgressTimelineProps) {
  const current = progress ?? fallbackProgress();

  return (
    <section className="rounded-[28px] border border-slate-200 bg-white px-5 py-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-slate-950">{current.label}</p>
          <p className="mt-1 text-xs text-slate-500">上传后会依次完成文本提取、结构化解析和评分。</p>
        </div>
        <span className="rounded-full bg-blue-50 px-3 py-1 text-sm font-semibold text-blue-700">{current.percent}%</span>
      </div>

      <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-100">
        <div className="h-full rounded-full bg-blue-600 transition-all" style={{ width: `${Math.max(0, Math.min(100, current.percent))}%` }} />
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-5">
        {current.stages.map((stage, index) => (
          <div key={stage.key} className="flex items-center gap-2 sm:block">
            <span className={`inline-flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold ${dotClass(stage.status)}`}>
              {stage.status === "done" ? "✓" : index + 1}
            </span>
            <p className={`mt-0 text-xs sm:mt-2 ${stage.status === "current" ? "font-semibold text-blue-700" : stage.status === "failed" ? "font-semibold text-rose-700" : "text-slate-500"}`}>
              {stage.label}
            </p>
          </div>
        ))}
      </div>

      {current.failure_reason ? (
        <p className="mt-4 rounded-2xl border border-rose-100 bg-rose-50 px-4 py-3 text-sm leading-6 text-rose-700">
          {current.failure_reason.message}
        </p>
      ) : null}
    </section>
  );
}
