import { render, screen } from "@testing-library/react";

import { AppHeader } from "@/components/app-header";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

vi.mock("@/lib/auth", () => ({
  clearTokens: vi.fn(),
  isAuthenticated: () => false,
}));

describe("AppHeader", () => {
  it("uses the Qingcheng AI brand instead of implementation-era copy", () => {
    render(<AppHeader />);

    expect(screen.getByText("青程 AI")).toBeInTheDocument();
    expect(screen.getByText("AI 求职助手")).toBeInTheDocument();
    expect(screen.queryByText("InternAgent")).not.toBeInTheDocument();
    expect(screen.queryByText("Internship Workspace")).not.toBeInTheDocument();
  });
});
