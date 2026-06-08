type InterviewRhythmBarProps = {
  roundIndex: number;
  maxRounds: number;
  status: string;
  agentState?: {
    difficulty?: number;
    remaining_focus?: string[];
    last_followup_strategy?: string;
  } | null;
  lastFeedback?: string;
};

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    asking: "出题中",
    waiting_user: "等待回答",
    evaluating: "评估中",
    followup: "追问",
    summary: "总结",
    finished: "已结束",
  };
  return labels[status] ?? status;
}

function strategyLabel(value?: string) {
  const labels: Record<string, string> = {
    clarify: "澄清",
    drill_down: "下钻",
    challenge: "挑战",
    transfer: "迁移",
  };
  return value ? labels[value] ?? value : "待定";
}

export function InterviewRhythmBar({ roundIndex, maxRounds, status, agentState, lastFeedback }: InterviewRhythmBarProps) {
  const focus = agentState?.remaining_focus?.[0] || "岗位匹配";
  const difficulty = agentState?.difficulty ?? 2;

  return (
    <section className="mx-auto mb-3 grid w-full max-w-3xl gap-2 rounded-3xl border border-slate-200 bg-white px-4 py-3 text-xs text-slate-600 shadow-sm sm:grid-cols-4">
      <span className="font-semibold text-slate-950">第 {roundIndex} / {maxRounds} 轮</span>
      <span>难度 {difficulty}</span>
      <span>考察 {focus}</span>
      <span>{statusLabel(status)} · {strategyLabel(agentState?.last_followup_strategy)}</span>
      {lastFeedback ? <p className="text-slate-500 sm:col-span-4">上一题：{lastFeedback}</p> : null}
    </section>
  );
}
