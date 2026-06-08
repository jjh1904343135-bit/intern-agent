import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import { TelegramBindCard } from "@/components/telegram-bind-card";

describe("TelegramBindCard", () => {
  it("shows bound state without forcing the user to generate a new code", () => {
    render(
      <TelegramBindCard
        onCreateBindCode={vi.fn()}
        status={{ bound: true, enabled: true, username: "qingcheng_user", chat_id_masked: "621***08" }}
      />,
    );

    expect(screen.getByText("已绑定")).toBeInTheDocument();
    expect(screen.getByText("@qingcheng_user · 621***08")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "绑定 Telegram" })).not.toBeInTheDocument();
  });

  it("generates a bind command and allows copying it", async () => {
    const onCreateBindCode = vi.fn().mockResolvedValue({
      code: "ABCD12",
      command: "/bind ABCD12",
      expires_at: "2026-06-04T12:00:00",
      ttl_minutes: 10,
    });
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });

    render(<TelegramBindCard onCreateBindCode={onCreateBindCode} />);

    fireEvent.click(screen.getByRole("button", { name: "绑定 Telegram" }));

    await waitFor(() => expect(screen.getByText("/bind ABCD12")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "复制绑定命令" }));
    await waitFor(() => expect(screen.getByText("已复制")).toBeInTheDocument());

    expect(onCreateBindCode).toHaveBeenCalledTimes(1);
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("/bind ABCD12");
  });
});
