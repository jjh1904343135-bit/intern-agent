import { EmptyState } from "@/components/empty-state";

export type ConversationMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  meta?: string;
  status?: string;
  feedbackScore?: number;
  dimensions?: Record<string, number>;
};

type ConversationThreadProps = {
  messages: ConversationMessage[];
  emptyTitle?: string;
  emptyDescription?: string;
};

function roleLabel(role: ConversationMessage["role"]) {
  if (role === "user") {
    return "我的消息";
  }
  if (role === "system") {
    return "系统消息";
  }
  return "助手消息";
}

export function ConversationThread({
  messages,
  emptyTitle = "还没有消息",
  emptyDescription = "在下方输入问题，青程 AI 会整理上下文并给出下一步动作。",
}: ConversationThreadProps) {
  if (messages.length === 0) {
    return (
      <div className="rounded-[28px] border border-dashed border-blue-200 bg-blue-50/60 px-5 py-8">
        <EmptyState description={emptyDescription} title={emptyTitle} />
      </div>
    );
  }

  return (
    <div className="flex max-h-[620px] flex-col gap-4 overflow-y-auto rounded-[32px] border border-slate-200 bg-slate-50/70 p-4">
      {messages.map((message) => {
        const isUser = message.role === "user";
        const label = roleLabel(message.role);

        return (
          <article
            aria-label={`${label}：${message.content}`}
            className={[
              "max-w-[86%] rounded-[28px] px-5 py-4 shadow-[0_12px_30px_rgba(15,23,42,0.06)]",
              isUser ? "self-end bg-blue-600 text-white" : "self-start border border-slate-200 bg-white text-slate-900",
            ].join(" ")}
            key={message.id}
          >
            <div className="flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em]">
              <span className={isUser ? "text-blue-100" : "text-blue-600"}>{label}</span>
              {message.meta ? <span className={isUser ? "text-blue-100" : "text-slate-400"}>{message.meta}</span> : null}
              {message.status ? <span className={isUser ? "text-blue-100" : "text-slate-400"}>{message.status}</span> : null}
              {typeof message.feedbackScore === "number" ? <span className="rounded-full bg-blue-50 px-2 py-1 text-blue-700">反馈分 {message.feedbackScore}</span> : null}
            </div>

            <p className="mt-3 whitespace-pre-wrap text-sm leading-7">{message.content}</p>

            {message.dimensions ? (
              <div className="mt-4 flex flex-wrap gap-2">
                {Object.entries(message.dimensions).map(([name, value]) => (
                  <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-600" key={name}>
                    {name} {value}
                  </span>
                ))}
              </div>
            ) : null}
          </article>
        );
      })}
    </div>
  );
}
