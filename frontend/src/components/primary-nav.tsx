import Link from "next/link";

const workspaceLinks = [
  { href: "/", label: "工作台" },
  { href: "/resume/upload", label: "简历" },
  { href: "/jobs", label: "岗位" },
  { href: "/applications", label: "投递" },
  { href: "/interview/start", label: "面试" },
  { href: "/chat", label: "AI 助手" },
];

type PrimaryNavProps = {
  authenticated: boolean;
  pathname?: string;
  onLogout: () => void;
};

export function PrimaryNav({ authenticated, pathname, onLogout }: PrimaryNavProps) {
  if (!authenticated) {
    return (
      <div className="flex flex-wrap items-center gap-3">
        <Link className="rounded-full border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 transition hover:border-blue-500 hover:text-blue-600" href="/auth/login">
          登录
        </Link>
        <Link className="rounded-full bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-700" href="/auth/register">
          注册
        </Link>
      </div>
    );
  }

  return (
    <nav className="flex flex-wrap items-center gap-2" aria-label="主导航">
      {workspaceLinks.map((item) => {
        const active = pathname === item.href;
        return (
          <Link
            key={item.href}
            className={`rounded-full px-4 py-2 text-sm font-medium transition ${
              active
                ? "bg-blue-600 text-white shadow-[0_10px_25px_rgba(37,99,235,0.22)]"
                : "border border-slate-200 text-slate-700 hover:border-blue-500 hover:text-blue-600"
            }`}
            href={item.href}
          >
            {item.label}
          </Link>
        );
      })}
      <button
        className="rounded-full border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 transition hover:border-rose-300 hover:text-rose-600"
        onClick={onLogout}
        type="button"
      >
        退出
      </button>
    </nav>
  );
}
