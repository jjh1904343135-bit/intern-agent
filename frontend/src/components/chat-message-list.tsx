"use client";

import { useEffect, useRef } from "react";

import { AgentTrace, type AgentTraceEvent } from "@/components/agent-trace";
import { isNearBottom } from "@/lib/scroll";

export type ChatRecommendation = {
  canonical_title?: string;
  raw_title?: string;
  function?: string;
  specialization?: string | null;
  company?: string;
  recommendation_score?: number;
  explanation?: string;
  matched_skills?: string[];
  missing_skills?: string[];
  application_priority?: string;
  source?: string;
  url?: string | null;
  apply_url?: string | null;
};

export type ChatSuggestedAction = {
  kind: string;
  label: string;
  href: string;
  description?: string;
};

export type ChatKnowledgeReference = {
  question?: string | null;
  section_path?: string[];
  score?: number;
  source_file?: string | null;
  chunk_index?: number | string | null;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  meta?: string;
  streaming?: boolean;
  interrupted?: boolean;
  recommendations?: ChatRecommendation[];
  suggestedActions?: ChatSuggestedAction[];
  knowledgeReferences?: ChatKnowledgeReference[];
  agentTrace?: AgentTraceEvent[];
};

type ChatMessageListProps = {
  title: string;
  messages: ChatMessage[];
  examples: string[];
  onExampleClick: (example: string) => void;
  onCopy?: (content: string) => void;
  onRegenerate?: (messageId: string) => void;
  onContinue?: (messageId: string) => void;
  enableRegenerate?: boolean;
  enableContinue?: boolean;
};

function roleLabel(role: ChatMessage["role"]) {
  if (role === "user") {
    return "用户消息";
  }
  if (role === "system") {
    return "系统消息";
  }
  return "助手消息";
}

function scoreLabel(score?: number) {
  if (typeof score !== "number") {
    return null;
  }
  return `推荐 ${Math.round(score * 100)}`;
}

function RecommendationList({ recommendations }: { recommendations?: ChatRecommendation[] }) {
  if (!recommendations?.length) {
    return null;
  }

  return (
    <div className="mt-4 space-y-2">
      {recommendations.slice(0, 3).map((item, index) => {
        const title = item.canonical_title || item.raw_title || "推荐岗位";
        const url = item.url || item.apply_url;
        return (
          <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm" key={`${title}-${index}`}>
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
              {item.company ? <span>{item.company}</span> : null}
              {item.source ? <span>来源 {item.source}</span> : null}
              {scoreLabel(item.recommendation_score) ? <span className="rounded-full bg-blue-50 px-2 py-0.5 text-blue-700">{scoreLabel(item.recommendation_score)}</span> : null}
              {item.application_priority ? <span className="rounded-full bg-slate-100 px-2 py-0.5 text-slate-600">优先级 {item.application_priority}</span> : null}
            </div>
            <div className="mt-1 text-sm font-medium text-slate-950">{title}</div>
            {item.raw_title && item.raw_title !== title ? <div className="mt-0.5 text-xs text-slate-400">原始：{item.raw_title}</div> : null}
            {item.explanation ? <p className="mt-2 text-sm leading-6 text-slate-600">{item.explanation}</p> : null}
            {item.matched_skills?.length ? <div className="mt-2 text-xs text-slate-500">匹配：{item.matched_skills.join("、")}</div> : null}
            {item.missing_skills?.length ? <div className="mt-1 text-xs text-amber-700">缺口：{item.missing_skills.join("、")}</div> : null}
            {url ? (
              <a className="mt-2 inline-flex text-xs font-medium text-blue-700 hover:text-blue-900" href={url} rel="noreferrer" target="_blank">
                去原站投递
              </a>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function SuggestedActions({ actions }: { actions?: ChatSuggestedAction[] }) {
  if (!actions?.length) {
    return null;
  }

  return (
    <div className="mt-4 flex flex-wrap gap-2">
      {actions.map((action) => (
        <a
          className="rounded-full border border-blue-100 bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700 transition hover:border-blue-200 hover:bg-blue-100"
          href={action.href}
          key={`${action.kind}-${action.href}`}
          title={action.description}
        >
          {action.label}
        </a>
      ))}
    </div>
  );
}

function KnowledgeReferences({ references }: { references?: ChatKnowledgeReference[] }) {
  if (!references?.length) {
    return null;
  }

  return (
    <div className="mt-4 rounded-2xl border border-blue-100 bg-blue-50/60 px-4 py-3 text-xs text-slate-600">
      <div className="font-medium text-blue-800">参考知识</div>
      <div className="mt-2 space-y-2">
        {references.slice(0, 3).map((reference, index) => {
          const title = reference.question || reference.source_file || "知识库片段";
          const section = reference.section_path?.length ? reference.section_path.join(" / ") : reference.source_file || "八股知识库";
          const chunk = reference.chunk_index !== null && reference.chunk_index !== undefined ? ` · chunk ${reference.chunk_index}` : "";
          return (
            <div className="rounded-xl bg-white/80 px-3 py-2" key={`${title}-${reference.chunk_index ?? index}`}>
              <div className="font-medium text-slate-800">{title}</div>
              <div className="mt-0.5 text-slate-500">{section}{chunk}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function ChatMessageList({
  title,
  messages,
  examples,
  onExampleClick,
  onCopy,
  onRegenerate,
  onContinue,
  enableRegenerate = true,
  enableContinue = false,
}: ChatMessageListProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const shouldAutoScrollRef = useRef(true);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }
    if (shouldAutoScrollRef.current && typeof bottomRef.current?.scrollIntoView === "function") {
      bottomRef.current.scrollIntoView({ block: "end", behavior: "smooth" });
    }
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex min-h-[56vh] flex-col items-center justify-center px-4 text-center">
        <h1 className="text-2xl font-semibold tracking-tight text-slate-950">{title}</h1>
        <div className="mt-8 grid w-full max-w-2xl gap-3 sm:grid-cols-2">
          {examples.map((example) => (
            <button
              className="rounded-2xl border border-slate-200 bg-white px-4 py-4 text-left text-sm leading-6 text-slate-700 shadow-sm transition hover:border-slate-300 hover:bg-slate-50"
              key={example}
              onClick={() => onExampleClick(example)}
              type="button"
            >
              {example}
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div
      className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 overflow-y-auto px-4 pb-36 pt-8"
      onScroll={(event) => {
        shouldAutoScrollRef.current = isNearBottom(event.currentTarget);
      }}
      ref={containerRef}
    >
      {messages.map((message) => {
        const isUser = message.role === "user";
        const showAssistantActions = message.role === "assistant" && !message.streaming;
        return (
          <article
            aria-label={`${roleLabel(message.role)}：${message.content}`}
            className={isUser ? "ml-auto max-w-[78%] rounded-3xl bg-slate-900 px-5 py-3 text-white" : "group mr-auto max-w-[88%] px-1 py-2 text-slate-900"}
            key={message.id}
          >
            <div className="whitespace-pre-wrap text-[15px] leading-7">
              {message.content}
              {message.streaming ? <span className="ml-1 inline-block h-4 w-1 animate-pulse rounded bg-slate-400 align-middle" /> : null}
            </div>
            <RecommendationList recommendations={message.recommendations} />
            <KnowledgeReferences references={message.knowledgeReferences} />
            <SuggestedActions actions={message.suggestedActions} />
            {message.agentTrace?.length ? <div className="mt-4"><AgentTrace events={message.agentTrace} /></div> : null}
            {message.meta ? <div className={`mt-2 text-xs ${isUser ? "text-slate-300" : "text-slate-400"}`}>{message.meta}</div> : null}
            {message.interrupted ? <div className="mt-2 text-xs text-amber-600">生成中断</div> : null}
            {showAssistantActions ? (
              <div className="mt-2 flex gap-2 text-xs text-slate-400 opacity-100 transition sm:opacity-0 sm:group-hover:opacity-100">
                {onCopy ? (
                  <button className="hover:text-slate-700" onClick={() => onCopy(message.content)} type="button">
                    复制
                  </button>
                ) : null}
                {enableRegenerate && onRegenerate ? (
                  <button className="hover:text-slate-700" onClick={() => onRegenerate(message.id)} type="button">
                    重新生成
                  </button>
                ) : null}
                {enableContinue && onContinue ? (
                  <button className="hover:text-slate-700" onClick={() => onContinue(message.id)} type="button">
                    继续生成
                  </button>
                ) : null}
              </div>
            ) : null}
          </article>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
