import React from "react";
import { render, screen } from "@testing-library/react";

import { MetricCard } from "@/components/metric-card";

describe("MetricCard", () => {
  it("renders title, value and hint", () => {
    render(React.createElement(MetricCard, { label: "简历评分", value: "84", hint: "Gemma4 最新评审", accent: "primary" }));

    expect(screen.getByText("简历评分")).toBeInTheDocument();
    expect(screen.getByText("84")).toBeInTheDocument();
    expect(screen.getByText("Gemma4 最新评审")).toBeInTheDocument();
  });
});
