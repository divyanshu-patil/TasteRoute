import { describe, expect, it } from "vitest";
import { initialProgress, reduce } from "./progress";
import type { RunEvent } from "./sse";

const ev = (id: number, type: string, payload: Record<string, unknown> = {}): RunEvent => ({ id, type, payload });

describe("progress reducer", () => {
  it("tracks steps, Qloo calls and the phase end", () => {
    let p = initialProgress;
    for (const e of [
      ev(1, "phase_started", { phase: "scout", orchestration: "agent", provider: "fake" }),
      ev(2, "tool_call", { tool: "rank_venues" }),
      ev(3, "qloo_call", { endpoint: "/v2/insights", status: 200, cache_hit: false, duration_ms: 812, result_count: 50 }),
      ev(4, "qloo_call", { endpoint: "/v2/insights", status: 200, cache_hit: true, result_count: 50 }),
      ev(5, "step_done", { tool: "rank_venues", summary: { ranked: 50, top: ["A", "B"] } }),
      ev(6, "warning", { code: "low_coverage", message: "Low coverage" }),
      ev(7, "warning", { code: "guard_refused", message: "refused" }),
      ev(8, "phase_done", { phase: "scout", orchestration: "agent" }),
    ]) p = reduce(p, e);
    expect(p.done).toEqual(["rank_venues"]);
    expect(p.active).toBeNull();
    expect([p.qlooLive, p.qlooCached]).toEqual([1, 1]);
    expect(p.warnings).toEqual(["Low coverage"]);
    expect(p.finished).toBe(true);
    expect(p.log.find((l) => l.kind === "done")?.text).toContain("ranked: 50");
  });

  it("ignores replayed events after a reconnect", () => {
    const once = reduce(initialProgress, ev(3, "qloo_call", { cache_hit: false }));
    const replayed = reduce(once, ev(3, "qloo_call", { cache_hit: false }));
    expect(replayed.qlooLive).toBe(1);
    expect(reduce(replayed, ev(2, "tool_call", { tool: "x" }))).toBe(replayed);
  });

  it("records failures", () => {
    const p = reduce(initialProgress, ev(1, "failed", { code: "qloo_auth", message: "Qloo rejected the key" }));
    expect(p.failed).toEqual({ code: "qloo_auth", message: "Qloo rejected the key" });
    expect(p.finished).toBe(true);
  });
});
