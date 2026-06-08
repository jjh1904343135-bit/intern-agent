"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { PrimaryNav } from "@/components/primary-nav";
import { clearTokens, isAuthenticated } from "@/lib/auth";

export function AppHeader() {
  const pathname = usePathname();
  const [mounted, setMounted] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);

  useEffect(() => {
    setMounted(true);
    setAuthenticated(isAuthenticated());
  }, []);

  function handleLogout() {
    clearTokens();
    window.location.assign("/auth/login");
  }

  return (
    <header className="sticky top-0 z-30 border-b border-slate-200/70 bg-white/95 backdrop-blur-xl">
      <div className="mx-auto flex w-full max-w-7xl items-center justify-between gap-4 px-4 py-3 sm:px-6 lg:px-8">
        <div className="flex items-center gap-4">
          <Link className="no-underline" href="/">
            <div className="inline-flex items-center gap-3 rounded-full border border-blue-100 bg-white px-3 py-2 shadow-sm shadow-blue-100/60">
              <span className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-blue-600 text-sm font-bold text-white">青</span>
              <div>
                <p className="text-base font-semibold leading-none text-slate-950">青程 AI</p>
                <p className="mt-1 text-xs text-slate-500">AI 求职助手</p>
              </div>
            </div>
          </Link>
        </div>

        {!mounted ? (
          <div className="h-11 w-48 rounded-full bg-slate-100" />
        ) : (
          <PrimaryNav authenticated={authenticated} onLogout={handleLogout} pathname={pathname} />
        )}
      </div>
    </header>
  );
}
