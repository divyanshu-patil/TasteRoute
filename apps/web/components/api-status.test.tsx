import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiStatus } from "./api-status";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("ApiStatus", () => {
  it("counts the wait while connecting, then reports how long the API took", async () => {
    vi.useFakeTimers();
    let answer: (r: { ok: boolean }) => void = () => {};
    const fetch = vi.fn(() => new Promise<{ ok: boolean }>((resolve) => { answer = resolve; }));
    vi.stubGlobal("fetch", fetch);
    render(<ApiStatus />);
    expect(screen.getByRole("button", { name: /Backend connecting/ })).toBeTruthy();
    await act(() => vi.advanceTimersByTimeAsync(4200));
    expect(screen.getByText(/API connecting · 4s/)).toBeTruthy();
    await act(async () => { answer({ ok: true }); });
    expect(screen.getByText(/API ready · 4\.2s/)).toBeTruthy();
    expect(fetch).toHaveBeenCalledWith(expect.stringMatching(/\/health$/), expect.objectContaining({ cache: "no-store" }));
  });

  it("says when the API can't be reached, keeps the 50s wake-up note, and retries on click", async () => {
    const fetch = vi.fn().mockRejectedValue(new Error("no network"));
    vi.stubGlobal("fetch", fetch);
    render(<ApiStatus />);
    const chip = await screen.findByRole("button", { name: /Backend unreachable/ });
    expect(chip.textContent).toContain("API unreachable · retry");
    expect(screen.getByRole("tooltip").textContent).toContain("up to 50s");
    fetch.mockResolvedValue({ ok: true });
    await act(async () => { chip.click(); });
    expect(await screen.findByRole("button", { name: /Backend ready/ })).toBeTruthy();
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});
