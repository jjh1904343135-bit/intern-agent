import { apiRequest, postSseStream } from "@/lib/api";
import { getAccessToken, setTokens } from "@/lib/auth";

describe("api auth error handling", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it("clears expired token and returns a friendly message for normal requests", async () => {
    setTokens("expired-token");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Signature has expired" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(apiRequest("/api/v1/dashboard/summary", { auth: true })).rejects.toThrow("登录已过期，请重新登录");
    expect(getAccessToken()).toBeNull();
  });

  it("clears expired token and returns a friendly message for SSE requests", async () => {
    setTokens("expired-token");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Signature has expired" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(postSseStream("/api/v1/chat/stream", { message: "你好" }, () => undefined)).rejects.toThrow("登录已过期，请重新登录");
    expect(getAccessToken()).toBeNull();
  });

  it("normalizes browser network failures for SSE requests", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("network error"));

    await expect(postSseStream("/api/v1/chat/stream", { message: "你好" }, () => undefined)).rejects.toThrow(
      "网络连接失败，请确认后端服务已启动",
    );
  });
});
