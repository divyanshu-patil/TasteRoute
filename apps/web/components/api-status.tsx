"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { API_URL } from "../lib/api";

/** The hosted API sleeps when idle (docs/16-runbook.md); its first request can take about this long to wake it. */
const WAKE_MS = 50_000;
/** A little past a worst-case wake-up, so a slow cold start is never reported as broken. */
const GIVE_UP_MS = WAKE_MS + 25_000;

const TIP =
  "This demo's API sleeps when idle to save on hosting. Waking it up can take up to 50s, so the first request may sit still: it is starting, not broken. Click to check again.";

type State = { kind: "checking" } | { kind: "ready"; ms: number } | { kind: "down" };

/** "0.4s" for a warm answer, "42s" for a cold start. */
function duration(ms: number): string {
  if (ms < 1000) return `${Math.max(1, Math.round(ms / 100)) / 10}s`;
  if (ms < 10_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms / 1000)}s`;
}

/** Small nav chip: is the API reachable, and how long the check is taking (a cold start can run to 50s). */
export function ApiStatus() {
  const [state, setState] = useState<State>({ kind: "checking" });
  const [elapsed, setElapsed] = useState(0);
  const busy = useRef(false);
  const lastOk = useRef(0); // a happy result stays good for two minutes before another check
  const tipId = useId();

  const check = useCallback(async () => {
    if (busy.current) return;
    busy.current = true;
    setElapsed(0);
    setState({ kind: "checking" });
    const t0 = performance.now();
    try {
      const r = await fetch(`${API_URL}/health`, { cache: "no-store", signal: AbortSignal.timeout(GIVE_UP_MS) });
      if (!r.ok) throw new Error(String(r.status));
      lastOk.current = Date.now();
      setState({ kind: "ready", ms: performance.now() - t0 });
    } catch {
      setState({ kind: "down" });
    } finally {
      busy.current = false;
    }
  }, []);

  // Check on load (which also starts the wake-up), and again when the tab comes back or the network does.
  useEffect(() => {
    void check();
    const again = () => {
      if (document.visibilityState === "visible" && Date.now() - lastOk.current > 120_000) void check();
    };
    document.addEventListener("visibilitychange", again);
    window.addEventListener("online", again);
    return () => {
      document.removeEventListener("visibilitychange", again);
      window.removeEventListener("online", again);
    };
  }, [check]);

  // The count while connecting, so a 40s wake-up doesn't look frozen.
  useEffect(() => {
    if (state.kind !== "checking") return;
    const t0 = Date.now();
    const id = setInterval(() => setElapsed(Date.now() - t0), 500);
    return () => clearInterval(id);
  }, [state]);

  const text =
    state.kind === "checking"
      ? `API connecting · ${Math.floor(elapsed / 1000)}s`
      : state.kind === "ready"
        ? `API ready · ${duration(state.ms)}`
        : "API unreachable · retry";

  const word = state.kind === "checking" ? "connecting" : state.kind === "ready" ? "ready" : "unreachable";
  const said =
    state.kind === "checking"
      ? "Connecting to the API."
      : state.kind === "ready"
        ? `API connected in ${duration(state.ms)}.`
        : "API unreachable. Click to try again.";

  return (
    <>
      <button
        type="button"
        className="api-status tip"
        data-state={state.kind}
        onClick={() => void check()}
        aria-label={`Backend ${word}. Check the connection now.`}
        aria-describedby={tipId}
      >
        <span className="dot" aria-hidden="true" />
        <span className="api-status-text" aria-hidden="true">{text}</span>
        <span className="tip-body" role="tooltip" id={tipId}>{TIP}</span>
      </button>
      <span className="sr-only" role="status">{said}</span>
    </>
  );
}
