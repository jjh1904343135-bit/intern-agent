import React from "react";
import { render, screen } from "@testing-library/react";

import { JobCard } from "@/components/job-card";

describe("JobCard", () => {
  it("shows real source, match score and manual application actions", () => {
    const onSave = vi.fn();

    render(
      React.createElement(JobCard, {
        job: {
          id: "job-1",
          title: "产品经理实习生",
          company: "腾讯",
          city: "上海",
          salary: "200-300/天",
          duration: null,
          deadline: null,
          source: "official_company",
          apply_url: "https://careers.tencent.com/tencentcareer/api/post/ByPostId?postId=job-1",
          jd_text: "负责用户研究、需求拆解和数据分析。",
          match_score: 91,
          job_type_label: "实习",
          market_region: "CN",
        },
        authenticated: true,
        onSave,
      }),
    );

    expect(screen.getByText("产品经理实习生")).toBeInTheDocument();
    expect(screen.getByText("腾讯")).toBeInTheDocument();
    expect(screen.getByText("来源 official_company")).toBeInTheDocument();
    expect(screen.getByText("91")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存到投递清单" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "去原站投递" })).toHaveAttribute("href", "https://careers.tencent.com/tencentcareer/api/post/ByPostId?postId=job-1");
    expect(screen.getByRole("link", { name: "查看详情" })).toHaveAttribute("href", "/jobs/job-1");
    expect(screen.getByText("实习")).toBeInTheDocument();
    expect(screen.getByText("中国优先")).toBeInTheDocument();
  });

  it("shows discovery metadata when canonical title and popularity are available", () => {
    const onSave = vi.fn();

    render(
      React.createElement(JobCard, {
        job: {
          id: "job-2",
          title: "Associate Product Manager Intern",
          raw_title: "Associate Product Manager Intern",
          canonical_title: "产品经理实习生",
          company: "字节跳动",
          city: "北京",
          salary: "250-350元/天",
          duration: "12 weeks",
          deadline: null,
          source: "official_company",
          apply_url: "https://jobs.bytedance.com/zh/position/2",
          jd_text: "Product operations, SQL and user research.",
          popularity_score: 88,
          skills: ["SQL", "User Research"],
          experience: "intern",
        },
        authenticated: false,
        onSave,
      }),
    );

    expect(screen.getByText("产品经理实习生")).toBeInTheDocument();
    expect(screen.getByText("原始标题：Associate Product Manager Intern")).toBeInTheDocument();
    expect(screen.getByText("热度 88")).toBeInTheDocument();
    expect(screen.getByText("SQL")).toBeInTheDocument();
    expect(screen.getByText("User Research")).toBeInTheDocument();
  });

  it("shows recommendation score, explanation and skill gaps compactly", () => {
    const onSave = vi.fn();

    render(
      React.createElement(JobCard, {
        job: {
          id: "job-3",
          title: "AI PM Intern",
          raw_title: "AI PM Intern",
          canonical_title: "AI Product Manager Intern",
          company: "腾讯",
          city: "上海",
          salary: null,
          duration: null,
          deadline: null,
          source: "official_company",
          apply_url: "https://careers.tencent.com/job/ai-pm",
          jd_text: "LLM product, SQL and user research.",
          recommendation_score: 0.86,
          application_priority: "high",
          explanation: "SQL 与用户研究匹配，LLM 产品经验需要补强。",
          matched_skills: ["SQL", "User Research"],
          missing_skills: ["LLM"],
        },
        authenticated: true,
        onSave,
      }),
    );

    expect(screen.getByText("推荐 86")).toBeInTheDocument();
    expect(screen.getByText("优先级 high")).toBeInTheDocument();
    expect(screen.getByText("推荐理由")).toBeInTheDocument();
    expect(screen.getByText("匹配技能")).toBeInTheDocument();
    expect(screen.getByText("缺失技能")).toBeInTheDocument();
    expect(screen.getByText("SQL 与用户研究匹配，LLM 产品经验需要补强。")).toBeInTheDocument();
    expect(screen.getByText("缺口：LLM")).toBeInTheDocument();
  });

  it("shows compact evidence dimensions when recommendation evidence is available", () => {
    const onSave = vi.fn();

    render(
      React.createElement(JobCard, {
        job: {
          id: "job-4",
          title: "Java 后端实习生",
          company: "腾讯",
          city: "北京",
          salary: "200-300/天",
          duration: null,
          deadline: null,
          source: "liepin_mcp",
          apply_url: "https://www.liepin.com/job/4",
          jd_text: "负责 Java、Redis、SQL 后端服务。",
          recommendation_score: 0.91,
          explanation: "技能和城市都匹配。",
          matched_skills: ["Java", "Redis"],
          missing_skills: ["Spring"],
          score_dimensions: [
            {
              dimension: "技能匹配",
              score: 0.67,
              weight: 0.5,
              evidence: ["简历命中 Java、Redis"],
              problems: ["缺少 Spring"],
              suggestions: ["补 Spring 项目证据"],
              confidence: 0.82,
            },
          ],
        },
        authenticated: true,
        onSave,
      }),
    );

    expect(screen.getByText("证据链")).toBeInTheDocument();
    expect(screen.getByText("技能匹配 67")).toBeInTheDocument();
    expect(screen.getByText("简历命中 Java、Redis")).toBeInTheDocument();
  });
});
