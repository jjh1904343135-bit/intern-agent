import { render, screen } from "@testing-library/react";

import { ChatFlowSvg, ProductPreviewSvg, ResumeFlowSvg } from "@/components/qingcheng-visuals";

describe("Qingcheng SVG visuals", () => {
  it("renders a product preview as an accessible inline svg", () => {
    render(<ProductPreviewSvg />);

    expect(screen.getByRole("img", { name: "青程 AI 产品预览" })).toBeInTheDocument();
    expect(screen.getByText("简历")).toBeInTheDocument();
    expect(screen.getByText("岗位")).toBeInTheDocument();
    expect(screen.getByText("投递")).toBeInTheDocument();
    expect(screen.getByText("面试")).toBeInTheDocument();
  });

  it("renders the resume parsing flow with stage labels", () => {
    render(<ResumeFlowSvg />);

    expect(screen.getByRole("img", { name: "简历解析流程预览" })).toBeInTheDocument();
    expect(screen.getByText("上传")).toBeInTheDocument();
    expect(screen.getByText("解析")).toBeInTheDocument();
    expect(screen.getByText("评分")).toBeInTheDocument();
  });

  it("renders the chat flow preview for assistant and interview pages", () => {
    render(<ChatFlowSvg />);

    expect(screen.getByRole("img", { name: "AI 对话流程预览" })).toBeInTheDocument();
    expect(screen.getByText("AI 助手")).toBeInTheDocument();
    expect(screen.getByText("岗位面试")).toBeInTheDocument();
  });
});
