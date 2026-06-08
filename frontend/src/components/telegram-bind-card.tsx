"use client";

import { useState } from "react";

export type TelegramBindPayload = {
  code: string;
  command: string;
  expires_at: string;
  ttl_minutes: number;
};

export type TelegramBindStatus = {
  bound: boolean;
  enabled: boolean;
  username?: string | null;
  first_name?: string | null;
  chat_id_masked?: string | null;
  last_seen_at?: string | null;
  chat_session_id?: string | null;
};

type TelegramBindCardProps = {
  onCreateBindCode: () => Promise<TelegramBindPayload>;
  loadingStatus?: boolean;
  status?: TelegramBindStatus | null;
};

function accountLabel(status: TelegramBindStatus) {
  const name = status.username ? `@${status.username}` : status.first_name || "Telegram";
  return status.chat_id_masked ? `${name} · ${status.chat_id_masked}` : name;
}

export function TelegramBindCard({ loadingStatus = false, onCreateBindCode, status }: TelegramBindCardProps) {
  const [payload, setPayload] = useState<TelegramBindPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const isBound = Boolean(status?.bound);

  async function createCode() {
    setLoading(true);
    setError("");
    setCopied(false);
    try {
      setPayload(await onCreateBindCode());
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "绑定码生成失败");
    } finally {
      setLoading(false);
    }
  }

  async function copyCommand() {
    if (!payload) {
      return;
    }
    await navigator.clipboard?.writeText(payload.command);
    setCopied(true);
  }

  return (
    <div className="mt-4 rounded-3xl border border-slate-100 bg-slate-50 p-3 text-xs text-slate-600">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="font-medium text-slate-900">Telegram</div>
          <div className="mt-0.5 text-slate-500">
            {loadingStatus ? "正在检查绑定状态" : isBound && status ? accountLabel(status) : "手机端继续使用 AI 助手"}
          </div>
        </div>
        {isBound ? (
          <span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 font-medium text-emerald-700">
            {status?.enabled ? "已绑定" : "已停用"}
          </span>
        ) : (
          <button
            className="rounded-full border border-blue-200 bg-white px-3 py-1.5 font-medium text-blue-700 transition hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={loading || loadingStatus}
            onClick={createCode}
            type="button"
          >
            {loading ? "生成中" : "绑定 Telegram"}
          </button>
        )}
      </div>

      {isBound ? (
        <div className="mt-3 rounded-2xl bg-white p-3 text-slate-500">
          已连接 Telegram，手机端消息会进入同一套 AI 助手会话和记忆。
        </div>
      ) : payload ? (
        <div className="mt-3 rounded-2xl bg-white p-3">
          <div className="font-mono text-sm text-slate-950">{payload.command}</div>
          <div className="mt-1 text-slate-400">请在 Telegram Bot 中发送，{payload.ttl_minutes} 分钟内有效。</div>
          <button className="mt-3 text-xs font-medium text-blue-700" onClick={copyCommand} type="button">
            {copied ? "已复制" : "复制绑定命令"}
          </button>
        </div>
      ) : null}

      {error ? <div className="mt-2 text-rose-600">{error}</div> : null}
    </div>
  );
}
