import React from "react";
import { render, screen } from "@testing-library/react";

import { InterviewRhythmBar } from "@/components/interview-rhythm-bar";

describe("InterviewRhythmBar", () => {
  it("shows round, difficulty, focus and last feedback without exposing agent internals", () => {
    render(
      React.createElement(InterviewRhythmBar, {
        roundIndex: 2,
        maxRounds: 3,
        status: "waiting_user",
        agentState: {
          difficulty: 4,
          remaining_focus: ["RAG", "项目复盘"],
          last_followup_strategy: "challenge",
        },
        lastFeedback: "回答具体，但还需要补充量化指标。",
      }),
    );

    expect(screen.getByText("第 2 / 3 轮")).toBeInTheDocument();
    expect(screen.getByText("难度 4")).toBeInTheDocument();
    expect(screen.getByText("考察 RAG")).toBeInTheDocument();
    expect(screen.getByText("上一题：回答具体，但还需要补充量化指标。")).toBeInTheDocument();
  });
});
