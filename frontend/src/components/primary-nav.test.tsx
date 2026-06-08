import React from "react";
import { render, screen } from "@testing-library/react";

import { PrimaryNav } from "@/components/primary-nav";

describe("PrimaryNav", () => {
  it("renders guest entry links when user is not authenticated", () => {
    render(React.createElement(PrimaryNav, { authenticated: false, onLogout: () => undefined }));

    expect(screen.getByRole("link", { name: "登录" })).toHaveAttribute("href", "/auth/login");
    expect(screen.getByRole("link", { name: "注册" })).toHaveAttribute("href", "/auth/register");
    expect(screen.queryByRole("button", { name: "退出" })).not.toBeInTheDocument();
  });

  it("renders workspace links and logout when user is authenticated", () => {
    render(React.createElement(PrimaryNav, { authenticated: true, onLogout: () => undefined }));

    expect(screen.getByRole("link", { name: "工作台" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "岗位" })).toHaveAttribute("href", "/jobs");
    expect(screen.getByRole("link", { name: "AI 助手" })).toHaveAttribute("href", "/chat");
    expect(screen.getByRole("button", { name: "退出" })).toBeInTheDocument();
  });
});
