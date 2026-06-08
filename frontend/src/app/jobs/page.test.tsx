import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import JobsPage from "@/app/jobs/page";
import { apiRequest } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  apiJson: vi.fn(),
  apiRequest: vi.fn(),
}));

vi.mock("@/lib/auth", () => ({
  clearTokens: vi.fn(),
  isAuthenticated: vi.fn(() => false),
}));

describe("JobsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    vi.mocked(apiRequest).mockResolvedValue({
      code: 0,
      data: {
        total: 1,
        jobs: [
          {
            id: "job-1",
            job_id: "job-1",
            title: "产品经理实习生",
            company: "字节跳动",
            city: "北京",
            salary: "220-300元/天",
            duration: null,
            deadline: null,
            posted_at: "2026-04-01T00:00:00",
            source: "official_company",
            apply_url: "https://jobs.bytedance.com/zh/position/job-1",
            jd_text: "负责产品需求和用户研究。",
            job_type_label: "实习",
            market_region: "CN",
          },
        ],
        source_status: {
          boss: { status: "blocked", reason: "captcha" },
          third_party_search: { status: "disabled", reason: "missing token" },
        },
      },
    });
  });

  it("loads jobs through unified search endpoint and renders the list item contract", async () => {
    render(React.createElement(JobsPage));

    await waitFor(() => expect(apiRequest).toHaveBeenCalled());
    expect(vi.mocked(apiRequest).mock.calls[0][0]).toContain("/api/v1/jobs/search?");
    expect(vi.mocked(apiRequest).mock.calls[0][0]).toContain("keyword=");
    expect(screen.getByText("产品经理实习生")).toBeInTheDocument();
    expect(screen.getByText("字节跳动")).toBeInTheDocument();
    expect(screen.getByText("220-300元/天")).toBeInTheDocument();
    expect(screen.getByText("来源 official_company")).toBeInTheDocument();
  });

  it("sends city and limit to unified search when filters are changed", async () => {
    render(React.createElement(JobsPage));
    await waitFor(() => expect(apiRequest).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByPlaceholderText("城市"), { target: { value: "北京" } });
    fireEvent.change(screen.getByPlaceholderText("数量"), { target: { value: "10" } });
    fireEvent.click(screen.getByRole("button", { name: "搜索" }));

    await waitFor(() => expect(apiRequest).toHaveBeenCalledTimes(2));
    expect(vi.mocked(apiRequest).mock.calls[1][0]).toContain("city=%E5%8C%97%E4%BA%AC");
    expect(vi.mocked(apiRequest).mock.calls[1][0]).toContain("limit=10");
  });

  it("shows product search suggestions and remembers filters", async () => {
    window.localStorage.setItem(
      "intern-agent:jobs:filters",
      JSON.stringify({ keyword: "产品", city: "上海", jobType: "intern", experience: "intern", limit: "10" }),
    );

    render(React.createElement(JobsPage));

    await waitFor(() => expect(apiRequest).toHaveBeenCalled());
    expect(screen.getByRole("button", { name: "产品经理实习" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "AIGC 产品" })).toBeInTheDocument();
    expect(screen.getByDisplayValue("上海")).toBeInTheDocument();
    expect(screen.getAllByDisplayValue("实习")).toHaveLength(2);

    fireEvent.change(screen.getByPlaceholderText("城市"), { target: { value: "北京" } });
    fireEvent.change(screen.getAllByDisplayValue("实习")[0], { target: { value: "full_time" } });

    await waitFor(() => {
      const saved = JSON.parse(window.localStorage.getItem("intern-agent:jobs:filters") || "{}");
      expect(saved.city).toBe("北京");
      expect(saved.jobType).toBe("full_time");
    });
  });

  it("does not mark Liepin as blocked when authorized MCP is available", async () => {
    vi.mocked(apiRequest).mockResolvedValueOnce({
      code: 0,
      data: {
        total: 1,
        jobs: [
          {
            id: "liepin-job-1",
            job_id: "liepin-job-1",
            title: "产品经理",
            company: "东方甄选",
            city: "北京",
            salary: "14-26k",
            duration: null,
            deadline: null,
            source: "liepin_mcp",
            apply_url: "https://www.liepin.com/job/1.shtml",
            jd_text: "真实猎聘岗位",
            job_type_label: "正式",
            market_region: "CN",
            live_posting: true,
          },
        ],
        source_status: {
          boss: { status: "blocked", reason: "captcha" },
          liepin: { status: "blocked", reason: "web scraping blocked" },
          liepin_mcp: { status: "ok", records: 157 },
          third_party_search: { status: "disabled", reason: "missing token" },
        },
      },
    });

    render(React.createElement(JobsPage));

    await waitFor(() => expect(screen.getByText("产品经理")).toBeInTheDocument());
    expect(screen.getByText(/猎聘 MCP 已接入/)).toBeInTheDocument();
    expect(screen.queryByText(/BOSS/)).not.toBeInTheDocument();
    expect(screen.queryByText(/猎聘网页.*不会被绕过/)).not.toBeInTheDocument();
  });
});
