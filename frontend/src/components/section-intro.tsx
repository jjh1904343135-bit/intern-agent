import type { ReactNode } from "react";

type SectionIntroProps = {
  eyebrow: string;
  title: string;
  description: string;
  actions?: ReactNode;
};

export function SectionIntro({ eyebrow, title, description, actions }: SectionIntroProps) {
  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div className="max-w-3xl">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-blue-600">{eyebrow}</p>
        <h1 className="mt-3 font-display text-3xl leading-tight text-slate-950 sm:text-4xl">{title}</h1>
        <p className="mt-3 text-sm leading-7 text-slate-500">{description}</p>
      </div>
      {actions ? <div className="flex flex-wrap gap-3">{actions}</div> : null}
    </div>
  );
}
