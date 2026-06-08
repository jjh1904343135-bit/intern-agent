"use client";

import type { KeyboardEvent } from "react";

type ChatComposerProps = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onStop: () => void;
  disabled?: boolean;
  isStreaming: boolean;
  placeholder?: string;
};

export function ChatComposer({
  value,
  onChange,
  onSubmit,
  onStop,
  disabled = false,
  isStreaming,
  placeholder = "输入消息...",
}: ChatComposerProps) {
  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey || isStreaming) {
      return;
    }
    event.preventDefault();
    onSubmit();
  }

  return (
    <form
      className="mx-auto w-full max-w-3xl rounded-[28px] border border-slate-200 bg-white p-3 shadow-[0_12px_36px_rgba(15,23,42,0.08)]"
      onSubmit={(event) => {
        event.preventDefault();
        if (!isStreaming) {
          onSubmit();
        }
      }}
    >
      <textarea
        aria-label="聊天输入"
        className="max-h-48 min-h-[72px] w-full resize-none rounded-[22px] border-0 bg-transparent px-3 py-3 text-[15px] leading-7 text-slate-900 outline-none placeholder:text-slate-400 focus:ring-0"
        disabled={disabled && !isStreaming}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        value={value}
      />
      <div className="flex items-center justify-between gap-3 px-1 pb-1">
        <span className="text-xs text-slate-400">Enter 发送 · Shift+Enter 换行</span>
        {isStreaming ? (
          <button className="rounded-full bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-700" onClick={onStop} type="button">
            停止
          </button>
        ) : (
          <button className="rounded-full bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40" disabled={disabled || !value.trim()} type="submit">
            发送
          </button>
        )}
      </div>
    </form>
  );
}
