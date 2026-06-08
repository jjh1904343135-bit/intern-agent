import { isNearBottom } from "@/lib/scroll";

describe("isNearBottom", () => {
  it("returns true when the user is close to the bottom", () => {
    const element = { scrollTop: 910, clientHeight: 100, scrollHeight: 1000 } as HTMLElement;

    expect(isNearBottom(element, 24)).toBe(true);
  });

  it("returns false when the user intentionally scrolled upward", () => {
    const element = { scrollTop: 300, clientHeight: 100, scrollHeight: 1000 } as HTMLElement;

    expect(isNearBottom(element, 80)).toBe(false);
  });
});
