import { StatusPill } from "@/components/status-pill";
import { formatStatusLabel } from "@/lib/format";

export type ResumeScore = {
  overall_score: number;
  label: string;
  rubric_version?: string;
  dimensions:
    | Record<string, number>
    | Array<{
        dimension: string;
        score: number;
        weight: number;
        evidence?: string[];
        problems?: string[];
        suggestions?: string[];
        confidence?: number;
      }>;
  highlights: string[];
  risks: string[];
  next_actions?: string[];
  summary?: string;
  source?: string;
  model?: string;
  status?: string;
};

type ResumeScoreCardProps = {
  fileName: string;
  parseStatus: string;
  skills?: string[];
  summary?: string;
  parseError?: string | null;
  score: ResumeScore | null;
};

function clampScore(value: number) {
  return Math.max(0, Math.min(100, value));
}

function normalizeDimensions(score: ResumeScore | null) {
  if (!score?.dimensions) {
    return [];
  }
  if (Array.isArray(score.dimensions)) {
    return score.dimensions.map((item) => ({
      name: item.dimension,
      value: clampScore(Number(item.score ?? 0)),
      weight: item.weight,
      evidence: item.evidence ?? [],
      problems: item.problems ?? [],
      suggestions: item.suggestions ?? [],
      confidence: item.confidence,
    }));
  }
  return Object.entries(score.dimensions).map(([name, value]) => ({
    name,
    value: clampScore(Number(value ?? 0)),
    weight: undefined,
    evidence: [],
    problems: [],
    suggestions: [],
    confidence: undefined,
  }));
}

function MiniList({ title, items }: { title: string; items: string[] }) {
  if (!items.length) {
    return null;
  }
  return (
    <div>
      <p className="text-[11px] font-semibold text-slate-500">{title}</p>
      <div className="mt-1 grid gap-1 text-xs leading-5 text-slate-600">
        {items.slice(0, 2).map((item) => <p key={item}>{item}</p>)}
      </div>
    </div>
  );
}

export function ResumeScoreCard({ fileName, parseStatus, skills = [], summary, parseError, score }: ResumeScoreCardProps) {
  const sourceLabel = score?.source ? `${score.source} / ${score.model ?? "未知模型"}` : "等待模型评审";
  const dimensions = normalizeDimensions(score);

  return (
    <article className="overflow-hidden rounded-[32px] border border-slate-200 bg-white shadow-[0_24px_60px_rgba(15,23,42,0.08)]">
      <div className="grid gap-6 bg-gradient-to-br from-blue-600 to-slate-950 p-6 text-white sm:p-8 lg:grid-cols-[0.78fr_1.22fr]">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.35em] text-blue-100">Resume Report</p>
          <p className="mt-5 text-7xl font-semibold leading-none">{score?.overall_score ?? "--"}</p>
          <p className="mt-3 text-sm text-blue-100">{score?.label ?? formatStatusLabel(parseStatus)}</p>
        </div>
        <div className="flex flex-col justify-between gap-5">
          <div>
            <h2 className="font-display text-4xl">{fileName}</h2>
            <p className="mt-4 text-sm leading-7 text-blue-50">{score?.summary || summary || "简历正在解析中，完成后这里会显示模型总结和可执行建议。"}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <StatusPill tone={parseStatus === "done" ? "success" : parseStatus === "failed" ? "warning" : "neutral"}>{formatStatusLabel(parseStatus)}</StatusPill>
            <StatusPill tone={score?.status === "fallback" ? "warning" : "success"}>{sourceLabel}</StatusPill>
            {score?.rubric_version ? <StatusPill tone="neutral">{score.rubric_version}</StatusPill> : null}
          </div>
        </div>
      </div>

      <div className="grid gap-6 p-6 sm:p-8 xl:grid-cols-[1.05fr_0.95fr]">
        <div className="space-y-6">
          {score ? (
            <div className="grid gap-4">
              {dimensions.map((dimension) => (
                <div key={dimension.name} className="rounded-[24px] border border-slate-200 bg-white px-4 py-4 shadow-sm">
                  <div className="mb-2 flex items-center justify-between text-sm">
                    <span className="font-medium text-slate-800">{dimension.name}</span>
                    <span className="font-semibold text-slate-950">{dimension.value}</span>
                  </div>
                  <div className="h-3 overflow-hidden rounded-full bg-slate-100">
                    <div className="h-full rounded-full bg-blue-600" style={{ width: `${dimension.value}%` }} />
                  </div>
                  {typeof dimension.weight === "number" || typeof dimension.confidence === "number" ? (
                    <p className="mt-2 text-xs text-slate-400">
                      {typeof dimension.weight === "number" ? `权重 ${Math.round(dimension.weight * 100)}%` : ""}
                      {typeof dimension.weight === "number" && typeof dimension.confidence === "number" ? " · " : ""}
                      {typeof dimension.confidence === "number" ? `置信度 ${Math.round(dimension.confidence * 100)}%` : ""}
                    </p>
                  ) : null}
                  <div className="mt-3 grid gap-3 rounded-[18px] bg-slate-50 px-3 py-3 sm:grid-cols-3">
                    <MiniList title="依据" items={dimension.evidence} />
                    <MiniList title="扣分点" items={dimension.problems} />
                    <MiniList title="怎么改" items={dimension.suggestions} />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-[28px] border border-slate-200 bg-slate-50 px-5 py-5 text-sm leading-7 text-slate-600">
              {parseStatus === "failed" ? parseError || "解析失败，请换一份 PDF/DOCX 后重试。" : "正在处理简历，稍后会自动生成评分报告。"}
            </div>
          )}

          <div className="rounded-[28px] border border-slate-200 bg-slate-50 px-5 py-5">
            <p className="text-sm font-semibold text-slate-900">技能关键词</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {skills.length > 0 ? skills.map((item) => <span key={item} className="rounded-full bg-white px-3 py-1 text-sm text-slate-700 shadow-sm">{item}</span>) : <span className="text-sm text-slate-500">暂无关键词</span>}
            </div>
          </div>
        </div>

        <div className="grid gap-4">
          <div className="rounded-[28px] border border-emerald-100 bg-emerald-50 px-5 py-5">
            <p className="text-sm font-semibold text-emerald-800">亮点</p>
            <div className="mt-3 grid gap-2 text-sm leading-6 text-emerald-900">
              {(score?.highlights.length ? score.highlights : ["评分完成后会显示简历亮点。"]).map((item) => <p key={item}>{item}</p>)}
            </div>
          </div>
          <div className="rounded-[28px] border border-rose-100 bg-rose-50 px-5 py-5">
            <p className="text-sm font-semibold text-rose-800">风险</p>
            <div className="mt-3 grid gap-2 text-sm leading-6 text-rose-900">
              {(score?.risks.length ? score.risks : ["评分完成后会显示优先修复点。 "]).map((item) => <p key={item}>{item}</p>)}
            </div>
          </div>
          <div className="rounded-[28px] border border-blue-100 bg-blue-50 px-5 py-5">
            <p className="text-sm font-semibold text-blue-800">下一步</p>
            <div className="mt-3 grid gap-2 text-sm leading-6 text-blue-950">
              {(score?.next_actions?.length ? score.next_actions : ["去岗位页查看真实岗位和匹配分。", "进入 AI 助手拆解下一步准备。 "]).map((item) => <p key={item}>{item}</p>)}
            </div>
          </div>
        </div>
      </div>
    </article>
  );
}
