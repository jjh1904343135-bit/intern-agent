"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";

import { PageShell } from "@/components/page-shell";
import { ProductPreviewSvg } from "@/components/qingcheng-visuals";
import { SectionIntro } from "@/components/section-intro";
import { SurfaceCard } from "@/components/surface-card";
import { apiJson, type ApiEnvelope } from "@/lib/api";
import { isAuthenticated, setTokens } from "@/lib/auth";

type RegisterPayload = {
  access_token: string;
  refresh_token: string;
};

export default function RegisterPage() {
  const [name, setName] = useState("");
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
      const payload = await apiJson<ApiEnvelope<RegisterPayload>>("/api/v1/auth/register", { name, email, password });
      setTokens(payload.data.access_token, payload.data.refresh_token);
      window.location.assign("/");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "注册失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <PageShell className="justify-center">
      <div className="mx-auto grid w-full max-w-5xl gap-6 xl:grid-cols-[1fr_1fr]">
        <SurfaceCard>
          <SectionIntro
            eyebrow="Create Account"
            title="创建青程账号"
            description="注册后进入工作台，继续上传简历、保存岗位和练面试。"
          />
          <form className="mt-8 grid gap-5" onSubmit={handleSubmit}>
            <label className="grid gap-2">
              <span className="text-sm font-medium text-slate-700">姓名</span>
              <input
                className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-slate-900"
                onChange={(event) => setName(event.target.value)}
                placeholder="你的名字"
                value={name}
              />
            </label>

            <label className="grid gap-2">
              <span className="text-sm font-medium text-slate-700">邮箱</span>
              <input
                className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-slate-900"
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@example.com"
                type="email"
                value={email}
              />
            </label>

            <label className="grid gap-2">
              <span className="text-sm font-medium text-slate-700">密码</span>
              <input
                className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-slate-900"
                onChange={(event) => setPassword(event.target.value)}
                placeholder="至少 8 位"
                type="password"
                value={password}
              />
            </label>

            {error ? <p className="rounded-2xl border border-rose-100 bg-rose-50 px-4 py-3 text-sm text-rose-600">{error}</p> : null}

            <button className="action-button w-full justify-center py-3 text-base" disabled={submitting} type="submit">
                {submitting ? "正在创建账号..." : "进入工作台"}
            </button>
          </form>

          <div className="mt-5 flex flex-wrap items-center justify-between gap-3 text-sm text-slate-500">
            <Link className="font-medium text-blue-600" href="/auth/login">
              已有账号？去登录
            </Link>
            <Link className="font-medium text-slate-600" href="/">
              返回访客首页
            </Link>
          </div>
        </SurfaceCard>

        <SurfaceCard className="bg-blue-600 text-white shadow-[0_24px_70px_rgba(37,99,235,0.22)]">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-blue-100">What You Get</p>
          <h1 className="mt-3 font-display text-3xl leading-tight text-white sm:text-4xl">一条清晰求职线</h1>
          <p className="mt-3 text-sm leading-7 text-blue-50">简历、岗位、投递、面试都围绕同一个账号沉淀。</p>
          <div className="mt-8 overflow-hidden rounded-[30px] bg-white/10 p-2">
            <ProductPreviewSvg />
          </div>
        </SurfaceCard>
      </div>
    </PageShell>
  );
}
