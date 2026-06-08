import { render, screen } from "@testing-library/react";

import { ConversationThread } from "@/components/conversation-thread";

describe("ConversationThread", () => {
  it("renders a compact empty state before the first message", () => {
    render(<ConversationThread emptyDescription="先发一个问题开始。" emptyTitle="还没有消息" messages={[]} />);

    expect(screen.getByText("还没有消息")).toBeInTheDocument();
    expect(screen.getByText("先发一个问题开始。")).toBeInTheDocument();
  });

  it("places user messages on the right and assistant messages on the left", () => {
    render(
      <ConversationThread
        messages={[
          { id: "user-1", role: "user", content: "我想练产品经理实习面试" },
          { id: "assistant-1", role: "assistant", content: "先用 STAR 结构回答。", meta: "gemma4:26b" },
        ]}
      />,
    );

    expect(screen.getByLabelText("我的消息：我想练产品经理实习面试")).toHaveClass("self-end");
    expect(screen.getByLabelText("助手消息：先用 STAR 结构回答。")).toHaveClass("self-start");
    expect(screen.getByText("gemma4:26b")).toBeInTheDocument();
  });

  it("shows interview feedback score and dimensions inside assistant bubbles", () => {
    render(
      <ConversationThread
        messages={[
          {
            id: "assistant-feedback",
            role: "assistant",
            content: "表达清楚，但结果量化不足。",
            feedbackScore: 82,
            dimensions: { 结构: 80, 结果: 75 },
          },
        ]}
      />,
    );

    expect(screen.getByText("反馈分 82")).toBeInTheDocument();
    expect(screen.getByText("结构 80")).toBeInTheDocument();
    expect(screen.getByText("结果 75")).toBeInTheDocument();
  });
});
