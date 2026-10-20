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

  it("logs a decision with who made it and why", () => {
    const p = reduce(initialProgress, ev(1, "decision", { tool: "add_venue_type", by: "AI agent", reason: "only 9 bars" }));
    expect(p.log[0]?.text).toBe("◆ AI agent chose add venue type: only 9 bars");
  });

  it("ignores replayed events after a reconnect", () => {
    const once = reduce(initialProgress, ev(3, "qloo_call", { cache_hit: false }));
    const replayed = reduce(once, ev(3, "qloo_call", { cache_hit: false }));
    expect(replayed.qlooLive).toBe(1);
    expect(reduce(replayed, ev(2, "tool_call", { tool: "x" }))).toBe(replayed);
  });

  it("starts clean for the outreach phase and follows each venue live", () => {
    let p = initialProgress;
    for (const e of [
      ev(1, "phase_started", { phase: "scout" }),
      ev(2, "qloo_call", { cache_hit: false }),
      ev(3, "phase_done", { phase: "scout" }),
      ev(4, "phase_started", { phase: "outreach" }),
      ev(5, "tool_call", { tool: "find_contacts" }),
      ev(6, "venue", { tool: "find_contacts", venue: "Cabin Juice", state: "checking", done: 0, of: 2 }),
      ev(7, "external_call", { service: "website", status: 200, cache_hit: false }),
      ev(8, "venue", { tool: "find_contacts", venue: "Cabin Juice", state: "done", result: "found", done: 1, of: 2 }),
      ev(9, "venue", { tool: "find_contacts", venue: "Safeway", state: "checking", done: 1, of: 2 }),
    ]) p = reduce(p, e);
    expect([p.phase, p.qlooLive, p.finished]).toEqual(["outreach", 0, false]); // the scout phase is not carried over
    expect(p.counts.find_contacts).toEqual({ done: 1, of: 2 });
    expect(p.current).toEqual({ tool: "find_contacts", venue: "Safeway" });
    expect(p.results).toEqual([{ id: 8, tool: "find_contacts", venue: "Cabin Juice", result: "found" }]);
    expect(p.log.map((l) => l.text)).toContain("website 200");
  });

  it("records failures", () => {
    const p = reduce(initialProgress, ev(1, "failed", { code: "qloo_auth", message: "Qloo rejected the key" }));
    expect(p.failed).toEqual({ code: "qloo_auth", message: "Qloo rejected the key" });
    expect(p.finished).toBe(true);
  });
});
