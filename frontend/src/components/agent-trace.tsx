"use client";

import { useState } from "react";

import { StatusPill } from "@/components/status-pill";
import { truncateText } from "@/lib/format";

export type AgentTraceEvent = {
  type: string;
  content?: string;
  agent?: string;
  source?: string;
  model?: string;
  status?: string;
  session_id?: string;
};

type AgentTraceProps = {
  events: AgentTraceEvent[];
};

export function AgentTrace({ events }: AgentTraceProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <section className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-[0_18px_50px_rgba(15,23,42,0.06)]">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.35em] text-blue-600">Agent Trace</p>
          <h2 className="mt-2 font-display text-3xl text-slate-950">运行轨迹</h2>
        </div>
        <button className="secondary-button" onClick={() => setExpanded((value) => !value)} type="button">
          {expanded ? "收起运行轨迹" : "展开运行轨迹"}
        </button>
      </div>

      <p className="mt-4 text-sm leading-7 text-slate-600">
        默认只展示最终建议。需要看项目亮点时，再展开查看意图、规划、工具调用和校验过程。
      </p>

      {expanded ? (
        <div className="mt-6 grid gap-3 text-sm">
          {events.length === 0 ? (
            <p className="rounded-[24px] border border-slate-200 bg-slate-50 px-4 py-4 text-slate-500">暂无轨迹，提交问题后会自动记录。</p>
          ) : (
            events.map((item, index) => (
              <article key={`${item.type}-${index}`} className="rounded-[24px] border border-slate-200 bg-slate-50 px-4 py-4">
                <div className="flex flex-wrap items-center gap-2">
                  <StatusPill>{item.type}</StatusPill>
                  {item.agent ? <span className="text-slate-500">agent: {item.agent}</span> : null}
                  {item.source ? <span className="text-slate-500">source: {item.source}</span> : null}
                </div>
                <p className="mt-3 leading-6 text-slate-600">{truncateText(item.content || "-", 240)}</p>
              </article>
            ))
          )}
        </div>
      ) : null}
    </section>
  );
}
