import type { RunEvent } from "./sse";

export type Progress = {
  lastId: number;
  phase: string | null;
  orchestration: string | null;
  done: string[];
  active: string | null;
  qlooLive: number;
  qlooCached: number;
  external: number;
  warnings: string[];
  log: { id: number; kind: "call" | "done" | "qloo" | "warn" | "phase" | "fail" | "web"; text: string }[];
  failed: { code: string; message: string } | null;
  finished: boolean;
  counts: Record<string, { done: number; of: number }>; // per tool, from "venue" events
  current: { tool: string; venue: string } | null; // the venue being worked on now
  results: { id: number; tool: string; venue: string; result: string }[];
};

export const initialProgress: Progress = {
  lastId: 0, phase: null, orchestration: null, done: [], active: null, qlooLive: 0, qlooCached: 0, external: 0,
  warnings: [], log: [], failed: null, finished: false, counts: {}, current: null, results: [],
};

const str = (v: unknown) => (typeof v === "string" ? v : v == null ? "" : JSON.stringify(v));

function summarise(s: Record<string, unknown>): string {
  return Object.entries(s)
    .filter(([k, v]) => !Array.isArray(v) || k === "top")
    .slice(0, 4)
    .map(([k, v]) => `${k.replace(/_/g, " ")}: ${Array.isArray(v) ? v.slice(0, 3).join(", ") : str(v)}`)
    .join(" · ");
}

/** Pure reducer over run events (ignores replays with ids it has already seen). */
export function reduce(p: Progress, e: RunEvent): Progress {
  if (e.id && e.id <= p.lastId) return p;
  const x = e.payload;
  const next: Progress = { ...p, lastId: e.id || p.lastId };
  const log = (kind: Progress["log"][number]["kind"], text: string) => {
    next.log = [...p.log, { id: e.id, kind, text }].slice(-80);
  };
  switch (e.type) {
    case "phase_started": // a new phase starts a clean panel (the stream replays earlier phases too)
      Object.assign(next, initialProgress, { lastId: next.lastId, phase: str(x.phase), orchestration: str(x.orchestration) });
      next.log = [{ id: e.id, kind: "phase", text: `${str(x.phase)} phase · ${str(x.provider)}` }];
      break;
    case "tool_call":
      next.active = str(x.tool);
      log("call", `→ ${str(x.tool)}`);
      break;
    case "decision": // AGT-07: a step the agent (or the fixed plan's same rule) chose, with its reason
      log("call", `◆ ${str(x.by)} chose ${str(x.tool).replace(/_/g, " ")}: ${str(x.reason)}`);
      break;
    case "step_done":
      next.done = p.done.includes(str(x.tool)) ? p.done : [...p.done, str(x.tool)];
      next.active = null;
      next.current = null;
      log("done", `✓ ${str(x.tool)}  ${summarise((x.summary as Record<string, unknown>) ?? {})}`);
      break;
    case "qloo_call":
      if (x.cache_hit) next.qlooCached = p.qlooCached + 1;
      else next.qlooLive = p.qlooLive + 1;
      log("qloo", `qloo ${str(x.endpoint)} ${str(x.status)}${x.cache_hit ? " cached" : ` ${str(x.duration_ms)}ms`} · ${str(x.result_count)} results`);
      break;
    case "external_call":
      next.external = p.external + 1;
      log("web", `${str(x.service)} ${str(x.status)}${x.cache_hit ? " cached" : ""}`);
      break;
    case "venue": {
      const tool = str(x.tool), venue = str(x.venue);
      next.counts = { ...p.counts, [tool]: { done: Number(x.done), of: Number(x.of) } };
      if (x.state === "checking") next.current = { tool, venue };
      else {
        if (p.current?.venue === venue) next.current = null;
        next.results = [...p.results, { id: e.id, tool, venue, result: str(x.result) }];
        log("done", `  ${venue}: ${str(x.result).replace(/_/g, " ")}`);
      }
      break;
    }
    case "warning":
      if (x.code !== "guard_refused") next.warnings = [...p.warnings, str(x.message)];
      log("warn", `! ${str(x.message)}`);
      break;
    case "phase_done":
      next.finished = true;
      next.active = null;
      next.current = null;
      next.orchestration = str(x.orchestration);
      log("phase", `${str(x.phase)} done · ${str(x.orchestration)}${x.reason ? ` (${str(x.reason)})` : ""}`);
      break;
    case "failed":
      next.failed = { code: str(x.code), message: str(x.message) };
      next.finished = true;
      next.active = null;
      log("fail", `✗ ${str(x.code)}: ${str(x.message)}`);
      break;
  }
  return next;
}
