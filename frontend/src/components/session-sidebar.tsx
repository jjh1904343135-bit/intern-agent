"use client";

import type { ReactNode } from "react";

export type SidebarSession = {
  id: string;
  title: string;
  subtitle?: string;
  preview?: string;
  summary?: string;
  lastQuestion?: string;
  completion?: string;
};

type SessionSidebarProps = {
  title: string;
  sessions: SidebarSession[];
  activeSessionId?: string | null;
  createLabel: string;
  emptyText: string;
  onCreate: () => void;
  onSelect: (sessionId: string) => void;
  footer?: ReactNode;
};

export function SessionSidebar({
  title,
  sessions,
  activeSessionId,
  createLabel,
  emptyText,
  onCreate,
  onSelect,
  footer,
}: SessionSidebarProps) {
  return (
    <aside className="hidden h-[calc(100vh-80px)] w-72 shrink-0 overflow-y-auto border-r border-slate-100 bg-white/95 px-3 py-4 lg:block">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
        <button
          className="rounded-full bg-blue-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-blue-700"
          onClick={onCreate}
          type="button"
        >
          {createLabel}
        </button>
      </div>

      {sessions.length === 0 ? (
        <p className="rounded-2xl bg-slate-50 px-4 py-5 text-sm leading-6 text-slate-500">{emptyText}</p>
      ) : (
        <div className="space-y-2">
          {sessions.map((session) => {
            const isActive = session.id === activeSessionId;
            return (
              <button
                aria-pressed={isActive}
                className={`w-full rounded-2xl px-3 py-3 text-left transition ${
                  isActive ? "bg-blue-50 text-blue-950" : "bg-white text-slate-700 hover:bg-slate-50"
                }`}
                key={session.id}
                onClick={() => onSelect(session.id)}
                type="button"
              >
                <div className="truncate text-sm font-medium">{session.title}</div>
                {session.subtitle ? <div className="mt-1 truncate text-xs text-slate-400">{session.subtitle}</div> : null}
                {session.summary ? <div className="mt-1 line-clamp-2 text-xs leading-5 text-slate-600">{session.summary}</div> : null}
                {session.lastQuestion ? <div className="mt-1 truncate text-xs text-slate-400">{session.lastQuestion}</div> : null}
                {session.completion ? <div className="mt-2 inline-flex rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-500">{session.completion}</div> : null}
                {!session.summary && session.preview ? <div className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">{session.preview}</div> : null}
              </button>
            );
          })}
        </div>
      )}
      {footer}
    </aside>
  );
}
