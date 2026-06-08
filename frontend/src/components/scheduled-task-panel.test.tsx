import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { ScheduledTaskPanel } from "@/components/scheduled-task-panel";

describe("ScheduledTaskPanel", () => {
  it("renders scheduled tasks and inbox actions", () => {
    const onRefresh = vi.fn();
    const onUpdateStatus = vi.fn();
    const onMarkRead = vi.fn();

    render(
      <ScheduledTaskPanel
        inbox={[{ inbox_id: "i1", title: "投递检查完成", content: "今天有 2 个待跟进事项。", status: "unread" }]}
        onMarkRead={onMarkRead}
        onRefresh={onRefresh}
        onUpdateStatus={onUpdateStatus}
        tasks={[{ task_id: "t1", title: "检查投递状态", instruction: "检查投递状态", status: "enabled", schedule_label: "每天 9 点", next_run_at_local: "2026-06-06T09:00:00" }]}
      />,
    );

    expect(screen.getByText("定时任务")).toBeInTheDocument();
    expect(screen.getByText("检查投递状态")).toBeInTheDocument();
    expect(screen.getByText("投递检查完成")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "刷新" }));
    fireEvent.click(screen.getByRole("button", { name: "暂停" }));
    fireEvent.click(screen.getByRole("button", { name: /投递检查完成/ }));

    expect(onRefresh).toHaveBeenCalledTimes(1);
    expect(onUpdateStatus).toHaveBeenCalledWith("t1", "paused");
    expect(onMarkRead).toHaveBeenCalledWith("i1");
  });

  it("shows empty states", () => {
    render(<ScheduledTaskPanel inbox={[]} onMarkRead={() => undefined} onRefresh={() => undefined} onUpdateStatus={() => undefined} tasks={[]} />);

    expect(screen.getByText(/暂无任务/)).toBeInTheDocument();
    expect(screen.getByText("还没有执行结果。")).toBeInTheDocument();
  });
});
