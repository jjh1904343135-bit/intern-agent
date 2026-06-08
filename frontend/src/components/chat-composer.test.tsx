import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { ChatComposer } from "@/components/chat-composer";

describe("ChatComposer", () => {
  it("submits with Enter and keeps Shift+Enter for new lines", () => {
    const onSubmit = vi.fn();
    render(<ChatComposer disabled={false} isStreaming={false} onChange={() => undefined} onStop={() => undefined} onSubmit={onSubmit} value="帮我找产品实习" />);

    const textbox = screen.getByRole("textbox");
    fireEvent.keyDown(textbox, { key: "Enter", shiftKey: true });
    expect(onSubmit).not.toHaveBeenCalled();

    fireEvent.keyDown(textbox, { key: "Enter" });
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("switches the primary action to stop while streaming", () => {
    const onStop = vi.fn();
    render(<ChatComposer disabled={false} isStreaming onChange={() => undefined} onStop={onStop} onSubmit={() => undefined} value="生成中" />);

    fireEvent.click(screen.getByRole("button", { name: "停止" }));
    expect(onStop).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: "发送" })).not.toBeInTheDocument();
  });
});
