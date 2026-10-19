import { api, type S } from "./api";

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

/** Send all: sends the drafts one at a time from the user's Gmail. Stops when Gmail wants permission again, so the rest
 * wait for the next click; the API sends each draft at most once, so nothing goes twice. */
export async function sendAll(
  drafts: { id: string; venue_name: string }[],
  googleToken: string,
  each: (done: number, sent: S["DraftOut"] | null) => void,
): Promise<{ sent: number; failed: string[]; reconnect: boolean }> {
  let sent = 0;
  const failed: string[] = [];
  for (const [i, d] of drafts.entries()) {
    try {
      const out = await api<S["DraftOut"]>(`/v1/drafts/${d.id}/send`, { method: "POST", body: { google_access_token: googleToken } });
      sent++;
      each(i + 1, out);
    } catch (e) {
      const err = e as { code?: string; detail?: string; title?: string };
      if (err.code === "gmail_reconnect") return { sent, failed, reconnect: true };
      failed.push(`${d.venue_name}: ${err.detail || err.title || "not sent"}`);
      each(i + 1, null);
    }
  }
  return { sent, failed, reconnect: false };
}
