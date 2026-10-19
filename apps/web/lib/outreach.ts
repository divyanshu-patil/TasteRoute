import { api } from "./api";

// The start request in flight. It outlives the results page, so the outreach page can show it and cancel it.
let pending: { runId: string; ctl: AbortController; done: Promise<unknown> } | null = null;

/** Starts finding contacts and drafting without waiting, so the outreach page can open at once. */
export function startOutreach(runId: string, venueIds: string[]): void {
  const ctl = new AbortController();
  const done = api(`/v1/runs/${runId}/contacts`, { method: "POST", body: { venue_ids: venueIds }, signal: ctl.signal });
  const mine = { runId, ctl, done };
  pending = mine;
  done.catch(() => undefined).finally(() => { if (pending === mine) pending = null; });
}

/** The start request for this run, if one hasn't answered yet. */
export const startingOutreach = (runId: string) => (pending?.runId === runId ? pending.done : null);

/** Drops a start that hasn't reached the API, then stops any outreach the API is already running. */
export async function cancelOutreach(runId: string): Promise<void> {
  if (pending?.runId === runId) pending.ctl.abort();
  await api(`/v1/runs/${runId}/cancel`, { method: "POST" });
}
