import React from "react";
import { render, screen } from "@testing-library/react";

import { JobDecisionPanel } from "@/components/job-decision-panel";
import type { JobCardItem } from "@/components/job-card";

describe("JobDecisionPanel", () => {
  it("turns a job detail into fit, resume, interview and action guidance", () => {
    const job: JobCardItem = {
      id: "job-1",
      title: "AI 产品经理实习生",
      company: "字节跳动",
      city: "北京",
      salary: "250-350元/天",
      duration: null,
      deadline: null,
      source: "official_company",
      apply_url: "https://jobs.bytedance.com/zh/position/job-1",
      jd_text: "负责 LLM 产品需求、SQL 数据分析、用户研究和跨团队沟通。",
      skills: ["SQL", "User Research", "LLM"],
      matched_skills: ["SQL", "User Research"],
      missing_skills: ["LLM"],
      explanation: "SQL 和用户研究匹配，LLM 产品经验需要补强。",
      recommendation_score: 0.82,
      application_priority: "high",
    };

    render(React.createElement(JobDecisionPanel, { job }));

    expect(screen.getByText("我适合吗")).toBeInTheDocument();
    expect(screen.getByText("简历怎么改")).toBeInTheDocument();
    expect(screen.getByText("面试可能问什么")).toBeInTheDocument();
    expect(screen.getByText(/SQL 和用户研究匹配/)).toBeInTheDocument();
    expect(screen.getByText(/补一条能证明 LLM 的项目/)).toBeInTheDocument();
    expect(screen.getByText(/请讲一个和 SQL 相关的项目/)).toBeInTheDocument();
  });
});
