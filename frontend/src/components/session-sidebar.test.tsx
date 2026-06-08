import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { SessionSidebar } from "@/components/session-sidebar";

describe("SessionSidebar", () => {
  it("renders sessions and emits create/select actions", () => {
    const onCreate = vi.fn();
    const onSelect = vi.fn();

    render(
      <SessionSidebar
        activeSessionId="s1"
        createLabel="新会话"
        emptyText="暂无会话"
        onCreate={onCreate}
        onSelect={onSelect}
        sessions={[
          { id: "s1", title: "帮我看简历风险", subtitle: "2 条消息", preview: "建议补充项目指标" },
          { id: "s2", title: "产品实习", subtitle: "1 轮", preview: "准备面试" },
        ]}
        title="会话"
      />,
    );

    expect(screen.getByText("会话")).toBeInTheDocument();
    expect(screen.getByText("帮我看简历风险")).toBeInTheDocument();
    expect(screen.getByText("建议补充项目指标")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "新会话" }));
    fireEvent.click(screen.getByRole("button", { name: /产品实习/ }));

    expect(onCreate).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith("s2");
  });

  it("renders session summary, last question, and completion when provided", () => {
    render(
      <SessionSidebar
        activeSessionId={null}
        createLabel="New"
        emptyText="Empty"
        onCreate={() => undefined}
        onSelect={() => undefined}
        sessions={[
          {
            id: "s3",
            title: "Product interview",
            subtitle: "Updated today",
            preview: "Old preview",
            summary: "Resume risk review",
            lastQuestion: "Why this role?",
            completion: "2/3 rounds",
          },
        ]}
        title="Sessions"
      />,
    );

    expect(screen.getByText("Resume risk review")).toBeInTheDocument();
    expect(screen.getByText("Why this role?")).toBeInTheDocument();
    expect(screen.getByText("2/3 rounds")).toBeInTheDocument();
  });
});
