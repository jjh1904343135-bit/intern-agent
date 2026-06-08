import type { ReactNode } from "react";

type PageShellProps = {
  children: ReactNode;
  className?: string;
};

export function PageShell({ children, className = "" }: PageShellProps) {
  return <main className={`mx-auto flex min-h-[calc(100vh-80px)] w-full max-w-7xl flex-col gap-6 px-4 py-8 sm:px-6 lg:px-8 ${className}`.trim()}>{children}</main>;
}
