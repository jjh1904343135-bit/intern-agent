"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { ChatComposer } from "@/components/chat-composer";
import { ChatMessageList, type ChatMessage } from "@/components/chat-message-list";
import { InterviewRhythmBar } from "@/components/interview-rhythm-bar";
import { PageShell } from "@/components/page-shell";
import { SessionSidebar, type SidebarSession } from "@/components/session-sidebar";
import { apiRequest, postSseStream, type ApiEnvelope } from "@/lib/api";

const examples = [
  "我会用 STAR 结构回答：背景、任务、行动、结果。",
  "这个项目里我负责接口设计、数据建模和测试保障。",
  "如果遇到线上问题，我会先止损，再定位根因并补监控。",
  "我想先澄清目标，再说明我如何拆解问题。",
];

type InterviewMessage = {
  id?: string;
  role: string;
  content: string;
  feedback_score?: number;
  source?: string;
  session_status?: string;
  round_index?: number;
};

type InterviewSessionPayload = {
  session_id: string;
  mode: string;
  job_title?: string | null;
  resume_file_name?: string | null;
  status: string;
  round_index: number;
  max_rounds: number;
  messages: InterviewMessage[];
  report?: {
    agent_state?: InterviewAgentState | null;
    agent_summary?: Record<string, unknown>;
  } | null;
  agent_state?: InterviewAgentState | null;
};

type InterviewAgentState = {
  difficulty?: number;
  remaining_focus?: string[];
  last_followup_strategy?: string;
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

type StreamPayload = {
  type?: string;
  conversation_id?: string;
  message_id?: string;
  content_delta?: string;
  full_content?: string;
  message?: string;
  metadata?: {
    model?: string;
    source?: string;
    status?: string;
    session_status?: string;
    round_index?: number;
    question_id?: string;
    feedback_score?: number;
    agent?: InterviewAgentState;
  };
};

function toChatMessages(messages: InterviewMessage[]): ChatMessage[] {
  return messages.map((message, index) => ({
    id: message.id ?? `${message.role}-${index}`,
    role: message.role === "assistant" ? "assistant" : "user",
    content: message.content,
    meta: message.feedback_score ? `第 ${message.round_index ?? "-"} 轮 · 反馈 ${message.feedback_score}` : message.session_status ?? message.source,
  }));
}

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

function makeMessageId(prefix: string) {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}`;
}

function lastFeedback(messages: ChatMessage[]) {
  const last = [...messages].reverse().find((message) => message.role === "assistant" && message.content.trim());
  if (!last) {
    return "";
  }
  return last.content.replace(/\s+/g, " ").slice(0, 60);
}

export default function InterviewSessionPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const sessionId = params.id;
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessions, setSessions] = useState<InterviewSessionSummary[]>([]);
  const [sessionMeta, setSessionMeta] = useState<InterviewSessionPayload | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  function upsertAssistantMessage(id: string, updater: (message: ChatMessage) => ChatMessage) {
    setMessages((current) => {
      const index = current.findIndex((message) => message.id === id);
      if (index === -1) {
        return [...current, updater({ id, role: "assistant", content: "", streaming: true })];
      }
      return current.map((message) => (message.id === id ? updater(message) : message));
    });
  }

  const loadSessions = useCallback(async () => {
    try {
      const response = await apiRequest<ApiEnvelope<InterviewSessionListPayload>>("/api/v1/interview/sessions", { auth: true });
      setSessions(response.data.sessions);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "面试列表加载失败");
    }
  }, []);

  const loadSession = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [detailResponse] = await Promise.all([
        apiRequest<ApiEnvelope<InterviewSessionPayload>>(`/api/v1/interview/session/${sessionId}`, { auth: true }),
        loadSessions(),
      ]);
      setSessionMeta(detailResponse.data);
      setMessages(toChatMessages(detailResponse.data.messages));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "面试会话加载失败");
    } finally {
      setLoading(false);
    }
  }, [loadSessions, sessionId]);

  useEffect(() => {
    void loadSession();
  }, [loadSession]);

  async function sendAnswer(text = input) {
    const trimmed = text.trim();
    if (!trimmed || isStreaming || sessionMeta?.status === "summary") {
      return;
    }

    const controller = new AbortController();
    abortRef.current = controller;
    setIsStreaming(true);
    setError("");
    setInput("");
    setMessages((current) => [...current, { id: makeMessageId("user"), role: "user", content: trimmed }]);

    try {
      await postSseStream(
        `/api/v1/interview/session/${sessionId}/answer/stream`,
        { answer: trimmed },
        (payload) => {
          const event = payload as StreamPayload;
          const messageId = event.message_id || makeMessageId("assistant");

          if (event.type === "start") {
            upsertAssistantMessage(messageId, (message) => ({
              ...message,
              meta: event.metadata?.model ?? "gemma4:26b",
              streaming: true,
            }));
            return;
          }

          if (event.type === "delta") {
            upsertAssistantMessage(messageId, (message) => ({
              ...message,
              content: `${message.content}${event.content_delta ?? ""}`,
              streaming: true,
            }));
            return;
          }

          if (event.type === "end") {
            upsertAssistantMessage(messageId, (message) => ({
              ...message,
              content: event.full_content ?? message.content,
              meta: typeof event.metadata?.feedback_score === "number" ? `第 ${event.metadata?.round_index ?? "-"} 轮 · 反馈 ${event.metadata.feedback_score}` : event.metadata?.session_status ?? event.metadata?.source ?? message.meta,
              streaming: false,
            }));
            if (event.metadata?.session_status) {
              setSessionMeta((current) =>
                current
                  ? {
                      ...current,
                      status: event.metadata?.session_status ?? current.status,
                      round_index: event.metadata?.round_index ?? current.round_index,
                      agent_state: {
                        ...(current.agent_state ?? current.report?.agent_state ?? {}),
                        ...(event.metadata?.agent ?? {}),
                      },
                    }
                  : current,
              );
            }
            void loadSessions();
            return;
          }

          if (event.type === "error") {
            setError(event.message ?? "面试反馈生成失败");
            setMessages((current) => current.map((message) => (message.streaming ? { ...message, streaming: false, meta: "生成失败" } : message)));
          }
        },
        { signal: controller.signal },
      );
    } catch (requestError) {
      if (controller.signal.aborted) {
        setMessages((current) => current.map((message) => (message.streaming ? { ...message, streaming: false, interrupted: true, meta: "已停止" } : message)));
        return;
      }
      setError(requestError instanceof Error ? requestError.message : "提交回答失败");
      setMessages((current) => current.map((message) => (message.streaming ? { ...message, streaming: false, meta: "生成失败" } : message)));
    } finally {
      setIsStreaming(false);
      abortRef.current = null;
    }
  }

  function stopStreaming() {
    abortRef.current?.abort();
    setIsStreaming(false);
  }

  const finished = sessionMeta?.status === "summary";

  return (
    <PageShell className="max-w-none gap-0 px-0 py-0">
      <div className="flex min-h-[calc(100vh-80px)] w-full bg-slate-50">
        <SessionSidebar
          activeSessionId={sessionId}
          createLabel="新面试"
          emptyText="暂无面试会话"
          onCreate={() => router.push("/interview/start")}
          onSelect={(targetSessionId) => router.push(`/interview/${targetSessionId}`)}
          sessions={sessions.map(toSidebarSession)}
          title="面试会话"
        />

        <div className="mx-auto flex min-h-[calc(100vh-80px)] w-full max-w-4xl flex-col">
          <div className="px-4 py-5 text-center">
            <h1 className="text-lg font-semibold tracking-tight text-slate-950">岗位模拟面试</h1>
            {sessionMeta ? (
              <p className="mt-1 text-xs text-slate-500">
                {sessionMeta.job_title ?? "目标岗位"} · 基于 {sessionMeta.resume_file_name ?? "默认简历"} · {sessionMeta.round_index}/{sessionMeta.max_rounds}
              </p>
            ) : null}
            {finished ? (
              <Link className="mt-2 inline-flex text-xs font-medium text-blue-600" href={`/interview/${sessionId}/report`}>
                查看面试报告
              </Link>
            ) : null}
          </div>

          {error ? <div className="mx-auto w-full max-w-3xl rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-600">{error}</div> : null}
          {loading ? <div className="mx-auto mt-12 text-sm text-slate-400">正在读取会话...</div> : null}
          {sessionMeta ? (
            <InterviewRhythmBar
              agentState={sessionMeta.agent_state ?? sessionMeta.report?.agent_state}
              lastFeedback={lastFeedback(messages)}
              maxRounds={sessionMeta.max_rounds}
              roundIndex={sessionMeta.round_index}
              status={sessionMeta.status}
            />
          ) : null}

          {!loading ? (
            <ChatMessageList
              enableRegenerate={false}
              examples={examples}
              messages={messages}
              onCopy={(content) => void navigator.clipboard?.writeText(content)}
              onExampleClick={setInput}
              title="开始回答面试官的问题"
            />
          ) : null}

          <div className="fixed inset-x-0 bottom-0 z-20 border-t border-slate-100 bg-slate-50/90 px-4 py-4 backdrop-blur lg:left-72">
            <ChatComposer
              disabled={loading || finished}
              isStreaming={isStreaming}
              onChange={setInput}
              onStop={stopStreaming}
              onSubmit={() => void sendAnswer()}
              placeholder={finished ? "本轮面试已完成，可以查看报告。" : "输入你的回答，面试官会边生成边反馈。"}
              value={input}
            />
          </div>
        </div>
      </div>
    </PageShell>
  );
}
