import Link from "next/link";

type EmptyStateAction = {
  href: string;
  label: string;
  tone?: "primary" | "secondary";
};

type EmptyStateProps = {
  title: string;
  description: string;
  actions?: EmptyStateAction[];
};

export function EmptyState({ title, description, actions = [] }: EmptyStateProps) {
  return (
    <div className="rounded-[28px] border border-dashed border-slate-200 bg-slate-50 px-6 py-8 text-center">
      <h2 className="text-xl font-semibold text-slate-900">{title}</h2>
      <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-slate-500">{description}</p>
      {actions.length > 0 ? (
        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          {actions.map((action) => (
            <Link
              key={`${action.href}-${action.label}`}
              className={
                action.tone === "secondary"
                  ? "rounded-full border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 transition hover:border-blue-500 hover:text-blue-600"
                  : "rounded-full bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-700"
              }
              href={action.href}
            >
              {action.label}
            </Link>
          ))}
        </div>
      ) : null}
    </div>
  );
}
