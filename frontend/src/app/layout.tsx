import type { Metadata } from "next";

import { AppHeader } from "@/components/app-header";

import "./globals.css";

export const metadata: Metadata = {
  title: "青程 AI",
  description: "青程 AI 求职助手，覆盖简历诊断、岗位匹配、投递追踪与 AI 面试训练。",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>
        <AppHeader />
        {children}
      </body>
    </html>
  );
}
