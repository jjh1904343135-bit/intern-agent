"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ChatComposer } from "@/components/chat-composer";
import { type AgentTraceEvent } from "@/components/agent-trace";
import { ChatMessageList, type ChatKnowledgeReference, type ChatMessage, type ChatRecommendation, type ChatSuggestedAction } from "@/components/chat-message-list";
import { PageShell } from "@/components/page-shell";
import { ScheduledTaskPanel, type ScheduledTaskItem, type TaskInboxItem } from "@/components/scheduled-task-panel";
import { SessionSidebar, type SidebarSession } from "@/components/session-sidebar";
import { TelegramBindCard, type TelegramBindPayload, type TelegramBindStatus } from "@/components/telegram-bind-card";
import { apiRequest, postSseStream, type ApiEnvelope } from "@/lib/api";

const examples = [
  "帮我找产品实习，并给我下一步行动。",
  "帮我看简历最大的三个风险。",
  "根据我的投递情况，安排未来 7 天计划。",
  "围绕我的项目经历，准备一轮面试追问。",
];

type ChatAction = "send" | "regenerate" | "continue";

// 后端 SSE metadata 是前端展示 Agent 工具、RAG 引用和定时任务状态的唯一入口。
type StreamPayload = {
  type?: string;
  conversation_id?: string;
  message_id?: string;
  role?: "assistant";
  content_delta?: string;
  full_content?: string;
  message?: string;
  metadata?: {
    model?: string;
    provider?: string;
    source?: string;
    status?: string;
    action?: ChatAction;
    interrupted?: boolean;
    agent_name?: string;
    agent_chain?: string[];
    agent_pipeline?: {
      phases?: string[];
    };
    tool_calls_summary?: Array<{
      name?: string;
      result_count?: number;
      available?: boolean;
      source_kind?: string | null;
      fallback_notice?: string | null;
    }>;
    recommendations?: ChatRecommendation[];
    suggested_actions?: ChatSuggestedAction[];
    scheduled_task_action?: string;
    scheduled_task_id?: string;
    schedule_summary?: string;
    next_run_at?: string;
    task_inbox_id?: string | null;
    fallback_notice?: string | null;
    knowledge_references?: {
      count?: number;
      source?: string | null;
      items?: ChatKnowledgeReference[];
    };
  };
};

type StoredChatMessage = {
  id?: string;
  role: "user" | "assistant" | "system";
  content: string;
  metadata?: StreamPayload["metadata"];
};

type ChatSessionSummary = {
  session_id: string;
  title: string;
  preview: string;
  summary?: string;
  last_question?: string;
  completion?: string;
  message_count: number;
  updated_at?: string | null;
};

type ChatSessionListPayload = {
  total: number;
  sessions: ChatSessionSummary[];
};

type ChatSessionDetailPayload = {
  session_id: string;
  messages: StoredChatMessage[];
};

type TelegramBindResponse = {
  code: string;
  command: string;
  expires_at: string;
  ttl_minutes: number;
};

type TelegramStatusResponse = TelegramBindStatus;

type ScheduledTasksPayload = {
  total: number;
  items: ScheduledTaskItem[];
};

type TaskInboxPayload = {
  total: number;
  items: TaskInboxItem[];
};

function makeMessageId(prefix: string) {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}`;
}

function metaLabel(metadata?: StreamPayload["metadata"]) {
  if (!metadata) {
    return "gemma4:26b";
  }
  if (metadata.interrupted) {
    return "已停止";
  }
  if (metadata.status === "fallback" && metadata.fallback_notice) {
    return `fallback：${metadata.fallback_notice}`;
  }
  if (metadata.knowledge_references?.count) {
    return `八股知识库 · ${metadata.knowledge_references.count} 条参考`;
  }
  return metadata.model ?? metadata.source ?? metadata.provider ?? "gemma4:26b";
}

function agentTraceFromMetadata(metadata?: StreamPayload["metadata"]): AgentTraceEvent[] | undefined {
  if (!metadata?.agent_name && !metadata?.agent_chain?.length && !metadata?.tool_calls_summary?.length) {
    return undefined;
  }
  const events: AgentTraceEvent[] = [];
  if (metadata.agent_chain?.length) {
    events.push({ type: "agent_chain", agent: metadata.agent_name, source: metadata.source, content: metadata.agent_chain.join(" → ") });
  } else if (metadata.agent_name) {
    events.push({ type: "agent_call", agent: metadata.agent_name, source: metadata.source, content: metadata.agent_name });
  }
  if (metadata.agent_pipeline?.phases?.length) {
    events.push({ type: "pipeline", agent: metadata.agent_name, status: metadata.status, content: metadata.agent_pipeline.phases.join(" → ") });
  }
  for (const tool of metadata.tool_calls_summary ?? []) {
    events.push({
      type: "tool_result",
      agent: metadata.agent_name,
      status: tool.fallback_notice ? "fallback" : undefined,
      content: `${tool.name ?? "tool"}: ${tool.result_count ?? (tool.available ? "available" : 0)}`,
    });
  }
  return events;
}

function toChatMessages(messages: StoredChatMessage[]): ChatMessage[] {
  return messages.map((message, index) => ({
    id: message.id ?? `${message.role}-${index}`,
    role: message.role,
    content: message.content,
    meta: message.role === "assistant" ? metaLabel(message.metadata) : undefined,
    interrupted: Boolean(message.metadata?.interrupted),
    recommendations: message.metadata?.recommendations,
    suggestedActions: message.metadata?.suggested_actions,
    knowledgeReferences: message.metadata?.knowledge_references?.items,
    agentTrace: message.role === "assistant" ? agentTraceFromMetadata(message.metadata) : undefined,
  }));
}

function toSidebarSession(session: ChatSessionSummary): SidebarSession {
  const updated = session.updated_at ? new Date(session.updated_at).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "最近更新";
  return {
    id: session.session_id,
    title: session.title || "新对话",
    subtitle: `${session.completion ?? `${session.message_count} 条消息`} · ${updated}`,
    preview: session.summary || session.preview,
    summary: session.summary,
    lastQuestion: session.last_question,
    completion: session.completion,
  };
}

export default function ChatPage() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [loadingScheduledTasks, setLoadingScheduledTasks] = useState(true);
  const [loadingTelegramStatus, setLoadingTelegramStatus] = useState(true);
  const [scheduledTasks, setScheduledTasks] = useState<ScheduledTaskItem[]>([]);
  const [taskInbox, setTaskInbox] = useState<TaskInboxItem[]>([]);
  const [telegramStatus, setTelegramStatus] = useState<TelegramBindStatus | null>(null);
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
    setLoadingSessions(true);
    try {
      const response = await apiRequest<ApiEnvelope<ChatSessionListPayload>>("/api/v1/chat/sessions", { auth: true });
      setSessions(response.data.sessions);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "会话列表加载失败");
    } finally {
      setLoadingSessions(false);
    }
  }, []);

  const loadSessionDetail = useCallback(async (targetSessionId: string) => {
    setError("");
    try {
      const response = await apiRequest<ApiEnvelope<ChatSessionDetailPayload>>(`/api/v1/chat/sessions/${targetSessionId}`, { auth: true });
      setSessionId(response.data.session_id);
      setMessages(toChatMessages(response.data.messages));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "会话加载失败");
    }
  }, []);

  const loadScheduledTasks = useCallback(async () => {
    setLoadingScheduledTasks(true);
    try {
      const [tasksResponse, inboxResponse] = await Promise.all([
        apiRequest<ApiEnvelope<ScheduledTasksPayload>>("/api/v1/scheduled-tasks", { auth: true }),
        apiRequest<ApiEnvelope<TaskInboxPayload>>("/api/v1/task-inbox", { auth: true }),
      ]);
      setScheduledTasks(tasksResponse.data.items);
      setTaskInbox(inboxResponse.data.items);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "定时任务加载失败");
    } finally {
      setLoadingScheduledTasks(false);
    }
  }, []);

  const loadTelegramStatus = useCallback(async () => {
    setLoadingTelegramStatus(true);
    try {
      const response = await apiRequest<ApiEnvelope<TelegramStatusResponse>>("/api/v1/telegram/status", { auth: true });
      setTelegramStatus(response.data);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Telegram 状态加载失败");
    } finally {
      setLoadingTelegramStatus(false);
    }
  }, []);

  useEffect(() => {
    void loadSessions();
    void loadScheduledTasks();
    void loadTelegramStatus();
  }, [loadScheduledTasks, loadSessions, loadTelegramStatus]);

  function newSession() {
    if (isStreaming) {
      return;
    }
    setSessionId(null);
    setMessages([]);
    setInput("");
    setError("");
  }

  async function copyMessage(content: string) {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      await navigator.clipboard.writeText(content);
    }
  }

  function prepareExistingAssistant(action: Exclude<ChatAction, "send">) {
    setMessages((current) => {
      const index = [...current].reverse().findIndex((message) => message.role === "assistant");
      if (index === -1) {
        return current;
      }
      const realIndex = current.length - 1 - index;
      return current.map((message, itemIndex) => {
        if (itemIndex !== realIndex) {
          return message;
        }
        if (action === "regenerate") {
          return { ...message, content: "", meta: "重新生成中", streaming: true, interrupted: false, recommendations: undefined };
        }
        return { ...message, meta: "继续生成中", streaming: true, interrupted: false };
      });
    });
  }

  async function sendMessage(text = input, action: ChatAction = "send") {
    const trimmed = text.trim();
    if ((action === "send" && !trimmed) || isStreaming) {
      return;
    }
    if (action !== "send" && !sessionId) {
      setError("当前还没有可继续的会话");
      return;
    }

    const controller = new AbortController();
    abortRef.current = controller;
    setIsStreaming(true);
    setError("");
    if (action === "send") {
      setInput("");
      setMessages((current) => [...current, { id: makeMessageId("user"), role: "user", content: trimmed }]);
    } else {
      prepareExistingAssistant(action);
    }

    try {
      await postSseStream(
        "/api/v1/chat/stream",
        { message: action === "send" ? trimmed : "", session_id: sessionId ?? "", action },
        (payload) => {
          const event = payload as StreamPayload;
          const messageId = event.message_id || makeMessageId("assistant");
          if (event.conversation_id) {
            setSessionId(event.conversation_id);
          }

          if (event.type === "start") {
            upsertAssistantMessage(messageId, (message) => ({
              ...message,
              meta: metaLabel(event.metadata),
              streaming: true,
              interrupted: false,
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
              meta: metaLabel(event.metadata),
              streaming: false,
              interrupted: Boolean(event.metadata?.interrupted),
              recommendations: event.metadata?.recommendations ?? message.recommendations,
              suggestedActions: event.metadata?.suggested_actions ?? message.suggestedActions,
              knowledgeReferences: event.metadata?.knowledge_references?.items ?? message.knowledgeReferences,
              agentTrace: agentTraceFromMetadata(event.metadata) ?? message.agentTrace,
            }));
            if (event.metadata?.scheduled_task_action) {
              // 创建、暂停、恢复、取消任务后刷新侧栏，保证任务收件箱和任务列表同步。
              void loadScheduledTasks();
            }
            void loadSessions();
            return;
          }

          if (event.type === "error") {
            setError(event.message ?? "生成失败");
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
      setError(requestError instanceof Error ? requestError.message : "对话请求失败");
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

  async function createTelegramBindCode(): Promise<TelegramBindPayload> {
    const response = await apiRequest<ApiEnvelope<TelegramBindResponse>>("/api/v1/telegram/bind-code", {
      method: "POST",
      auth: true,
    });
    return response.data;
  }

  async function updateScheduledTaskStatus(taskId: string, status: "enabled" | "paused" | "cancelled") {
    try {
      await apiRequest<ApiEnvelope<ScheduledTaskItem>>(`/api/v1/scheduled-tasks/${taskId}`, {
        method: "PATCH",
        auth: true,
        body: JSON.stringify({ status }),
      });
      await loadScheduledTasks();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "任务状态更新失败");
    }
  }

  async function markInboxRead(inboxId: string) {
    try {
      await apiRequest<ApiEnvelope<TaskInboxItem>>(`/api/v1/task-inbox/${inboxId}/read`, {
        method: "PATCH",
        auth: true,
      });
      await loadScheduledTasks();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "收件箱状态更新失败");
    }
  }

  return (
    <PageShell className="max-w-none gap-0 px-0 py-0">
      <div className="flex min-h-[calc(100vh-80px)] w-full bg-slate-50">
        <SessionSidebar
          activeSessionId={sessionId}
          createLabel="新对话"
          emptyText={loadingSessions ? "正在读取会话..." : "暂无历史会话"}
          onCreate={newSession}
          onSelect={(targetSessionId) => void loadSessionDetail(targetSessionId)}
          sessions={sessions.map(toSidebarSession)}
          title="AI 会话"
          footer={
            <div>
              {/* 任务面板和 Telegram 绑定都挂在 AI 会话侧栏；它们复用同一个 ChatService 后端。 */}
              <ScheduledTaskPanel
                inbox={taskInbox}
                loading={loadingScheduledTasks}
                onMarkRead={(inboxId) => void markInboxRead(inboxId)}
                onRefresh={() => void loadScheduledTasks()}
                onUpdateStatus={(taskId, status) => void updateScheduledTaskStatus(taskId, status)}
                tasks={scheduledTasks}
              />
              <TelegramBindCard
                loadingStatus={loadingTelegramStatus}
                onCreateBindCode={createTelegramBindCode}
                status={telegramStatus}
              />
            </div>
          }
        />

        <div className="mx-auto flex min-h-[calc(100vh-80px)] w-full max-w-4xl flex-col">
          <div className="px-4 py-5 text-center">
            <h1 className="text-lg font-semibold tracking-tight text-slate-950">青程 AI 助手</h1>
          </div>

          {error ? <div className="mx-auto w-full max-w-3xl rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-600">{error}</div> : null}

          <ChatMessageList
            enableContinue
            examples={examples}
            messages={messages}
            onContinue={() => void sendMessage("", "continue")}
            onCopy={(content) => void copyMessage(content)}
            onExampleClick={setInput}
            onRegenerate={() => void sendMessage("", "regenerate")}
            title="今天想解决什么求职问题？"
          />

          <div className="fixed inset-x-0 bottom-0 z-20 border-t border-slate-100 bg-slate-50/90 px-4 py-4 backdrop-blur lg:left-72">
            <ChatComposer
              disabled={false}
              isStreaming={isStreaming}
              onChange={setInput}
              onStop={stopStreaming}
              onSubmit={() => void sendMessage()}
              placeholder="输入你的求职问题，青程 AI 会边生成边回答。"
              value={input}
            />
          </div>
        </div>
      </div>
    </PageShell>
  );
}
