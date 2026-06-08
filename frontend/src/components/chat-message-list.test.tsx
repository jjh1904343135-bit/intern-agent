import { fireEvent, render, screen } from "@testing-library/react";

import { ChatMessageList } from "@/components/chat-message-list";

describe("ChatMessageList", () => {
  it("renders examples before conversation starts", () => {
    render(
      <ChatMessageList
        examples={["帮我找产品实习", "模拟一轮后端面试"]}
        messages={[]}
        onExampleClick={() => undefined}
        title="AI 助手"
      />,
    );

    expect(screen.getByText("帮我找产品实习")).toBeInTheDocument();
    expect(screen.getByText("模拟一轮后端面试")).toBeInTheDocument();
  });

  it("renders a minimal conversation and hides examples once messages exist", () => {
    render(
      <ChatMessageList
        examples={["帮我找产品实习"]}
        messages={[
          { id: "u1", role: "user", content: "我想找产品实习" },
          { id: "a1", role: "assistant", content: "先看你的简历和岗位要求。" },
        ]}
        onExampleClick={() => undefined}
        title="AI 助手"
      />,
    );

    expect(screen.getByLabelText("用户消息：我想找产品实习")).toBeInTheDocument();
    expect(screen.getByLabelText("助手消息：先看你的简历和岗位要求。")).toBeInTheDocument();
    expect(screen.queryByText("帮我找产品实习")).not.toBeInTheDocument();
  });

  it("renders lightweight assistant actions for copy and regenerate", () => {
    const onCopy = vi.fn();
    const onRegenerate = vi.fn();

    render(
      <ChatMessageList
        examples={[]}
        messages={[{ id: "a1", role: "assistant", content: "建议先投递匹配度最高的岗位。" }]}
        onCopy={onCopy}
        onExampleClick={() => undefined}
        onRegenerate={onRegenerate}
        title="AI 助手"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "复制" }));
    fireEvent.click(screen.getByRole("button", { name: "重新生成" }));

    expect(onCopy).toHaveBeenCalledWith("建议先投递匹配度最高的岗位。");
    expect(onRegenerate).toHaveBeenCalledWith("a1");
  });

  it("renders compact recommendation metadata inside assistant messages", () => {
    render(
      <ChatMessageList
        examples={[]}
        messages={[
          {
            id: "a1",
            role: "assistant",
            content: "我找到了一些适合先投的岗位。",
            recommendations: [
              {
                canonical_title: "AI 产品经理实习生",
                raw_title: "AI PM Intern",
                company: "腾讯",
                recommendation_score: 0.86,
                explanation: "SQL 与用户研究匹配，LLM 产品经验需要补强。",
                matched_skills: ["SQL", "User Research"],
                missing_skills: ["LLM"],
                application_priority: "high",
                source: "official_company",
                url: "https://careers.tencent.com/job/1",
              },
            ],
          },
        ]}
        onExampleClick={() => undefined}
        title="AI 助手"
      />,
    );

    expect(screen.getByText("AI 产品经理实习生")).toBeInTheDocument();
    expect(screen.getByText("推荐 86")).toBeInTheDocument();
    expect(screen.getByText("优先级 high")).toBeInTheDocument();
    expect(screen.getByText("缺口：LLM")).toBeInTheDocument();
  });

  it("renders suggested action links below assistant answers", () => {
    render(
      <ChatMessageList
        examples={[]}
        messages={[
          {
            id: "a-actions",
            role: "assistant",
            content: "下一步可以这样做。",
            suggestedActions: [
              { kind: "job_search", label: "搜索岗位", href: "/jobs?keyword=Product" },
              { kind: "interview_start", label: "开始面试", href: "/interview/start" },
            ],
          },
        ]}
        onExampleClick={() => undefined}
        title="AI 助手"
      />,
    );

    expect(screen.getByRole("link", { name: "搜索岗位" })).toHaveAttribute("href", "/jobs?keyword=Product");
    expect(screen.getByRole("link", { name: "开始面试" })).toHaveAttribute("href", "/interview/start");
  });

  it("renders compact knowledge references below technical answers", () => {
    render(
      <ChatMessageList
        examples={[]}
        messages={[
          {
            id: "a-rag",
            role: "assistant",
            content: "JVM 运行时数据区可以按线程共享和线程私有来回答。",
            knowledgeReferences: [
              {
                question: "JVM 内存模型",
                section_path: ["Java", "JVM"],
                score: 0.91,
                source_file: "10万字总结.docx",
                chunk_index: 12,
              },
            ],
          },
        ]}
        onExampleClick={() => undefined}
        title="AI 助手"
      />,
    );

    expect(screen.getByText("参考知识")).toBeInTheDocument();
    expect(screen.getByText("JVM 内存模型")).toBeInTheDocument();
    expect(screen.getByText("Java / JVM · chunk 12")).toBeInTheDocument();
  });

  it("renders assistant agent trace collapsed by default", () => {
    render(
      <ChatMessageList
        examples={[]}
        messages={[
          {
            id: "a-trace",
            role: "assistant",
            content: "我会先读取简历再检索岗位。",
            agentTrace: [
              { type: "agent_chain", agent: "chat_assistant", content: "supervisor → chat_assistant" },
              { type: "tool_result", agent: "chat_assistant", content: "job_search: 3" },
            ],
          },
        ]}
        onExampleClick={() => undefined}
        title="AI 助手"
      />,
    );

    expect(screen.getByText("Agent Trace")).toBeInTheDocument();
    expect(screen.queryByText("supervisor → chat_assistant")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "展开运行轨迹" }));

    expect(screen.getByText("supervisor → chat_assistant")).toBeInTheDocument();
    expect(screen.getByText("job_search: 3")).toBeInTheDocument();
  });
});
