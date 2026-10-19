"use client";

import { useCallback, useEffect, useReducer, useState } from "react";
import { ApiError, api, type S } from "./api";
import { initialProgress, reduce } from "./progress";
import { subscribeRun } from "./sse";

export const TERMINAL = ["scouted", "done", "failed"];

/** Loads a run, follows its SSE stream while it is running, and refetches when a phase ends. */
export function useRun(id: string) {
  const [run, setRun] = useState<S["RunOut"] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [progress, dispatch] = useReducer(reduce, initialProgress);
  const [online, setOnline] = useState(true);
  const [version, setVersion] = useState(0);
  const refresh = useCallback(() => setVersion((v) => v + 1), []);

  useEffect(() => {
    let alive = true;
    api<S["RunOut"]>(`/v1/runs/${id}`)
      .then((r) => alive && setRun(r))
      .catch((e: unknown) => alive && setError(e instanceof ApiError ? e : new ApiError(0, "error", "Failed to load", "")));
    return () => {
      alive = false;
    };
  }, [id, version]);

  const status = run?.status;
  useEffect(() => {
    if (!status || TERMINAL.includes(status)) return;
    return subscribeRun(
      id,
      (e) => {
        dispatch(e);
        if (e.type === "phase_done" || e.type === "failed") refresh();
      },
      refresh,
      setOnline,
    );
  }, [id, status, refresh]);

  return { run, error, progress, online, refresh };
}
