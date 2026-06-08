type MetricCardProps = {
  label: string;
  value: string | number;
  hint: string;
  accent?: "primary" | "neutral";
};

export function MetricCard({ label, value, hint, accent = "neutral" }: MetricCardProps) {
  const classes =
    accent === "primary"
      ? "border-blue-200 bg-blue-600 text-white shadow-[0_18px_45px_rgba(37,99,235,0.2)]"
      : "border-slate-200 bg-white text-slate-900 shadow-[0_18px_45px_rgba(15,23,42,0.06)]";

  const hintClasses = accent === "primary" ? "text-blue-100" : "text-slate-500";
  const labelClasses = accent === "primary" ? "text-blue-100" : "text-slate-500";

  return (
    <article className={`rounded-3xl border p-5 ${classes}`}>
      <p className={`text-xs font-semibold uppercase tracking-[0.24em] ${labelClasses}`}>{label}</p>
      <p className="mt-4 text-4xl font-semibold">{value}</p>
      <p className={`mt-2 text-sm ${hintClasses}`}>{hint}</p>
    </article>
  );
}
