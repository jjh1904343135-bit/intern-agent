import Link from "next/link";

import type { JobCardItem } from "@/components/job-card";

type JobDecisionPanelProps = {
  job: JobCardItem;
};

function scoreText(score?: number) {
  if (typeof score !== "number") {
    return "上传简历后生成";
  }
  return `${Math.round(score * 100)} 分`;
}

function buildResumeAdvice(job: JobCardItem) {
  const missing = job.missing_skills?.length ? job.missing_skills : job.skills?.slice(0, 2) ?? [];
  if (!missing.length) {
    return ["补一条和岗位职责直接相关的量化结果。", "把项目描述改成：问题、行动、结果。"];
  }
  return missing.slice(0, 3).map((skill) => `补一条能证明 ${skill} 的项目、指标或学习证据。`);
}

function buildInterviewQuestions(job: JobCardItem) {
  const skills = job.skills?.length ? job.skills : [job.canonical_title || job.title];
  return skills.slice(0, 3).map((skill) => `请讲一个和 ${skill} 相关的项目，你具体负责什么？`);
}

export function JobDecisionPanel({ job }: JobDecisionPanelProps) {
  const fitReason = job.explanation || "上传简历后，青程 AI 会结合技能、项目和城市偏好生成匹配解释。";
  const priority = job.application_priority === "high" ? "优先投递" : job.application_priority === "medium" ? "可以投递" : "先补材料";

  return (
    <section className="grid gap-4 lg:grid-cols-3">
      <div className="rounded-[24px] border border-blue-100 bg-blue-50 px-5 py-5">
        <p className="text-sm font-semibold text-blue-950">我适合吗</p>
        <p className="mt-3 text-3xl font-semibold text-blue-700">{scoreText(job.recommendation_score)}</p>
        <p className="mt-3 text-sm leading-6 text-blue-950">{fitReason}</p>
        <p className="mt-3 text-xs font-semibold text-blue-700">{priority}</p>
      </div>

      <div className="rounded-[24px] border border-slate-200 bg-white px-5 py-5">
        <p className="text-sm font-semibold text-slate-950">简历怎么改</p>
        <div className="mt-3 grid gap-2 text-sm leading-6 text-slate-600">
          {buildResumeAdvice(job).map((item) => (
            <p key={item}>{item}</p>
          ))}
        </div>
      </div>

      <div className="rounded-[24px] border border-slate-200 bg-white px-5 py-5">
        <p className="text-sm font-semibold text-slate-950">面试可能问什么</p>
        <div className="mt-3 grid gap-2 text-sm leading-6 text-slate-600">
          {buildInterviewQuestions(job).map((item) => (
            <p key={item}>{item}</p>
          ))}
        </div>
        <Link className="mt-4 inline-flex text-sm font-semibold text-blue-600" href={`/interview/start?jobId=${job.job_id || job.id}`}>
          开始岗位面试
        </Link>
      </div>
    </section>
  );
}
