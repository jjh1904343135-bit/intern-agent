"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";

import { PageShell } from "@/components/page-shell";
import { ChatFlowSvg } from "@/components/qingcheng-visuals";
import { SectionIntro } from "@/components/section-intro";
import { SurfaceCard } from "@/components/surface-card";
import { apiJson, type ApiEnvelope } from "@/lib/api";
import { isAuthenticated, setTokens } from "@/lib/auth";

type LoginPayload = {
  access_token: string;
  refresh_token: string;
};

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (isAuthenticated()) {
      window.location.replace("/");
    }
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");

    try {
      const payload = await apiJson<ApiEnvelope<LoginPayload>>("/api/v1/auth/login", { email, password });
      setTokens(payload.data.access_token, payload.data.refresh_token);
      window.location.assign("/");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "登录失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <PageShell className="justify-center">
      <div className="mx-auto grid w-full max-w-5xl gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <SurfaceCard className="bg-blue-600 text-white shadow-[0_22px_60px_rgba(37,99,235,0.2)]">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-blue-100">Qingcheng AI</p>
          <h1 className="mt-3 font-display text-3xl leading-tight text-white sm:text-4xl">回到青程 AI</h1>
          <p className="mt-3 text-sm leading-7 text-blue-50">继续看简历、岗位、投递和面试。</p>
          <div className="mt-8 overflow-hidden rounded-[30px] bg-white/10 p-2">
            <ChatFlowSvg />
          </div>
        </SurfaceCard>

        <SurfaceCard>
          <div className="mx-auto w-full max-w-xl">
            <SectionIntro
              eyebrow="Login"
              title="登录账号"
              description="测试账号：admin@example.com / password。"
            />

            <form className="mt-8 grid gap-5" onSubmit={handleSubmit}>
              <label className="grid gap-2">
                <span className="text-sm font-medium text-slate-700">账号</span>
                <input
                  className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-slate-900"
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="admin@example.com"
                  type="text"
                  value={email}
                />
              </label>

              <label className="grid gap-2">
                <span className="text-sm font-medium text-slate-700">密码</span>
                <input
                  className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-slate-900"
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="请输入登录密码"
                  type="password"
                  value={password}
                />
              </label>

              {error ? <p className="rounded-2xl border border-rose-100 bg-rose-50 px-4 py-3 text-sm text-rose-600">{error}</p> : null}

              <button className="action-button w-full justify-center py-3 text-base" disabled={submitting} type="submit">
                {submitting ? "正在登录..." : "进入工作台"}
              </button>
            </form>

            <div className="mt-5 flex flex-wrap items-center justify-between gap-3 text-sm text-slate-500">
              <Link className="font-medium text-blue-600" href="/auth/register">
                没有账号？去注册
              </Link>
              <Link className="font-medium text-slate-600" href="/">
                返回访客首页
              </Link>
            </div>
          </div>
        </SurfaceCard>
      </div>
    </PageShell>
  );
}
