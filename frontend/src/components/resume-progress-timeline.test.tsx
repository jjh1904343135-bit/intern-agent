import React from "react";
import { render, screen } from "@testing-library/react";

import { ResumeProgressTimeline, type ResumeProgress } from "@/components/resume-progress-timeline";

describe("ResumeProgressTimeline", () => {
  it("renders staged resume parsing progress and the current label", () => {
    const progress: ResumeProgress = {
      current_stage: "structuring",
      percent: 55,
      label: "正在结构化解析",
      stages: [
        { key: "uploaded", label: "上传成功", status: "done" },
        { key: "extracting_text", label: "正在提取文本", status: "done" },
        { key: "structuring", label: "正在结构化解析", status: "current" },
        { key: "scoring", label: "正在评分", status: "pending" },
        { key: "completed", label: "完成", status: "pending" },
      ],
      failure_reason: null,
    };

    render(React.createElement(ResumeProgressTimeline, { progress }));

    expect(screen.getAllByText("正在结构化解析")).toHaveLength(2);
    expect(screen.getByText("55%")).toBeInTheDocument();
    expect(screen.getByText("上传成功")).toBeInTheDocument();
    expect(screen.getByText("正在评分")).toBeInTheDocument();
  });

  it("shows specific failure reasons when parsing fails", () => {
    const progress: ResumeProgress = {
      current_stage: "failed",
      percent: 55,
      label: "解析失败",
      stages: [
        { key: "uploaded", label: "上传成功", status: "done" },
        { key: "extracting_text", label: "正在提取文本", status: "failed" },
        { key: "structuring", label: "正在结构化解析", status: "pending" },
        { key: "scoring", label: "正在评分", status: "pending" },
        { key: "completed", label: "完成", status: "pending" },
      ],
      failure_reason: { code: "text_too_short", message: "简历可提取文本太少，请换一份文本版 PDF/DOCX。" },
    };

    render(React.createElement(ResumeProgressTimeline, { progress }));

    expect(screen.getByText("解析失败")).toBeInTheDocument();
    expect(screen.getByText("简历可提取文本太少，请换一份文本版 PDF/DOCX。")).toBeInTheDocument();
  });
});
