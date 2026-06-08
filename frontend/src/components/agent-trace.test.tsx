import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";

import { AgentTrace } from "@/components/agent-trace";

describe("AgentTrace", () => {
  it("keeps agent events collapsed by default and expands on demand", () => {
    render(
      React.createElement(AgentTrace, {
        events: [
          { type: "thinking", content: "理解意图" },
          { type: "plan", content: "规划岗位检索" },
          { type: "tool_result", content: "找到 5 个岗位" },
          { type: "validation", content: "结果可用" },
        ],
      }),
    );

    expect(screen.getByText("Agent Trace")).toBeInTheDocument();
    expect(screen.queryByText("规划岗位检索")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "展开运行轨迹" }));

    expect(screen.getByText("规划岗位检索")).toBeInTheDocument();
    expect(screen.getByText("找到 5 个岗位")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "收起运行轨迹" })).toBeInTheDocument();
  });
});
