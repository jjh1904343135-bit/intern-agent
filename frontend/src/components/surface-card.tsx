import type { ReactNode } from "react";

type SurfaceCardProps = {
  children: ReactNode;
  className?: string;
};

export function SurfaceCard({ children, className = "" }: SurfaceCardProps) {
  return (
    <section
      className={`rounded-[28px] border border-slate-200/80 bg-white p-5 shadow-[0_18px_48px_rgba(15,23,42,0.06)] sm:p-7 ${className}`.trim()}
    >
      {children}
    </section>
  );
}
