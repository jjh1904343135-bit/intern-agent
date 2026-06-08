import React from "react";
import { render, screen } from "@testing-library/react";

import { ResumeScoreCard } from "@/components/resume-score-card";

describe("ResumeScoreCard", () => {
  it("renders a concise resume report without leaking engineering ids", () => {
    render(
      React.createElement(ResumeScoreCard, {
        fileName: "product-resume.docx",
        parseStatus: "done",
        skills: ["Python", "SQL"],
        score: {
          overall_score: 86,
          label: "有竞争力",
          summary: "项目经历完整，适合产品实习投递。",
          rubric_version: "resume_score_v1",
          dimensions: [
            {
              dimension: "项目经历",
              score: 88,
              weight: 0.25,
              evidence: ["简历中包含 InternAgent 项目"],
              problems: ["缺少量化指标"],
              suggestions: ["补充接口响应时间、检索命中率、测试覆盖率"],
              confidence: 0.86,
            },
            {
              dimension: "技能匹配",
              score: 82,
              weight: 0.2,
              evidence: ["Python、SQL 与目标岗位相关"],
              problems: ["缺少产品岗位关键词"],
              suggestions: ["补充用户研究或需求分析关键词"],
              confidence: 0.8,
            },
          ],
          highlights: ["有数据分析项目"],
          risks: ["量化结果还可以更具体"],
          next_actions: ["优先投递产品运营和数据产品岗位"],
          source: "gemma4",
          model: "gemma4:26b",
          status: "ready",
        },
      }),
    );

    expect(screen.getByText("86")).toBeInTheDocument();
    expect(screen.getByText("product-resume.docx")).toBeInTheDocument();
    expect(screen.getByText("gemma4 / gemma4:26b")).toBeInTheDocument();
    expect(screen.getByText("resume_score_v1")).toBeInTheDocument();
    expect(screen.getByText("项目经历")).toBeInTheDocument();
    expect(screen.getAllByText("依据").length).toBeGreaterThan(0);
    expect(screen.getByText("简历中包含 InternAgent 项目")).toBeInTheDocument();
    expect(screen.getAllByText("扣分点").length).toBeGreaterThan(0);
    expect(screen.getByText("缺少量化指标")).toBeInTheDocument();
    expect(screen.getAllByText("怎么改").length).toBeGreaterThan(0);
    expect(screen.getByText("补充接口响应时间、检索命中率、测试覆盖率")).toBeInTheDocument();
    expect(screen.getByText("量化结果还可以更具体")).toBeInTheDocument();
    expect(screen.getByText("优先投递产品运营和数据产品岗位")).toBeInTheDocument();
    expect(screen.queryByText(/resume_id/i)).not.toBeInTheDocument();
  });
});
