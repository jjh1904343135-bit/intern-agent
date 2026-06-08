"use client";

export type ScheduledTaskItem = {
  task_id: string;
  title: string;
  instruction: string;
  status: string;
  schedule_label: string;
  next_run_at_local?: string | null;
  last_error?: string | null;
};

export type TaskInboxItem = {
  inbox_id: string;
  task_id?: string | null;
  title: string;
  content: string;
  status: string;
  created_at?: string | null;
};

type ScheduledTaskPanelProps = {
  tasks: ScheduledTaskItem[];
  inbox: TaskInboxItem[];
  loading?: boolean;
  onRefresh: () => void;
  onUpdateStatus: (taskId: string, status: "enabled" | "paused" | "cancelled") => void;
  onMarkRead: (inboxId: string) => void;
};

function statusText(status: string) {
  return {
    enabled: "运行中",
    paused: "已暂停",
    cancelled: "已取消",
    completed: "已完成",
    running: "执行中",
  }[status] ?? status;
}

function shortTime(value?: string | null) {
  if (!value) {
    return "暂无";
  }
  return value.replace("T", " ").slice(5, 16);
}

export function ScheduledTaskPanel({ tasks, inbox, loading, onRefresh, onUpdateStatus, onMarkRead }: ScheduledTaskPanelProps) {
  return (
    <section className="mt-4 rounded-3xl border border-blue-100 bg-blue-50/50 p-3 text-xs text-slate-600">
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="font-medium text-slate-950">定时任务</div>
          <div className="mt-0.5 text-slate-500">到点执行，结果进收件箱</div>
        </div>
        <button className="rounded-full bg-white px-3 py-1.5 font-medium text-blue-700 shadow-sm" onClick={onRefresh} type="button">
          刷新
        </button>
      </div>

      <div className="mt-3 space-y-2">
        {loading ? <div className="rounded-2xl bg-white px-3 py-3 text-slate-400">正在读取任务...</div> : null}
        {!loading && tasks.length === 0 ? <div className="rounded-2xl bg-white px-3 py-3 text-slate-400">暂无任务，直接在聊天里说“明天 9 点提醒我”。</div> : null}
        {tasks.slice(0, 4).map((task) => (
          <div className="rounded-2xl bg-white p-3 shadow-sm" key={task.task_id}>
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate font-medium text-slate-950">{task.title}</div>
                <div className="mt-1 text-slate-500">{task.schedule_label} · {shortTime(task.next_run_at_local)}</div>
              </div>
              <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[11px] font-medium text-blue-700">{statusText(task.status)}</span>
            </div>
            {task.last_error ? <div className="mt-2 text-rose-600">{task.last_error}</div> : null}
            <div className="mt-3 flex flex-wrap gap-2">
              {task.status === "paused" ? (
                <button className="text-blue-700" onClick={() => onUpdateStatus(task.task_id, "enabled")} type="button">恢复</button>
              ) : (
                <button className="text-slate-500" onClick={() => onUpdateStatus(task.task_id, "paused")} type="button">暂停</button>
              )}
              <button className="text-rose-500" onClick={() => onUpdateStatus(task.task_id, "cancelled")} type="button">取消</button>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4 border-t border-blue-100 pt-3">
        <div className="mb-2 font-medium text-slate-950">任务收件箱</div>
        {inbox.length === 0 ? <div className="rounded-2xl bg-white px-3 py-3 text-slate-400">还没有执行结果。</div> : null}
        <div className="space-y-2">
          {inbox.slice(0, 3).map((item) => (
            <button
              className={`w-full rounded-2xl bg-white p-3 text-left shadow-sm ${item.status === "unread" ? "ring-1 ring-blue-100" : ""}`}
              key={item.inbox_id}
              onClick={() => onMarkRead(item.inbox_id)}
              type="button"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-medium text-slate-950">{item.title}</span>
                {item.status === "unread" ? <span className="rounded-full bg-blue-600 px-2 py-0.5 text-[10px] text-white">新</span> : null}
              </div>
              <div className="mt-1 line-clamp-2 text-slate-500">{item.content}</div>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
