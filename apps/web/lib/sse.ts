import { API_URL, api, type S } from "./api";

export type RunEvent = { id: number; type: string; payload: Record<string, unknown> };
export const EVENT_TYPES = [
  "phase_started", "tool_call", "step_done", "qloo_call", "external_call", "warning", "phase_done", "failed", "venue", "decision",
] as const;

/** EventSource with a short-lived token for this run only (EventSource can't send headers, so the workspace token never
 * goes in the URL). The browser reconnects with Last-Event-ID and the API replays; once the token expires, the stream
 * closes and a fresh token reopens it from the last event seen. */
export function subscribeRun(
  runId: string,
  onEvent: (e: RunEvent) => void,
  onEnd: () => void,
  onConnection: (online: boolean) => void,
): () => void {
  let es: EventSource | null = null;
  let closed = false;
  let last = 0;
  const open = () =>
    api<S["EventsToken"]>(`/v1/runs/${runId}/events-token`, { method: "POST" }).then(({ token }) => {
      if (closed) return;
      es = new EventSource(`${API_URL}/v1/runs/${runId}/events?token=${encodeURIComponent(token)}&last_event_id=${last}`);
      for (const type of EVENT_TYPES) {
        es.addEventListener(type, (m) => {
          const msg = m as MessageEvent<string>;
          last = Math.max(last, Number(msg.lastEventId) || 0);
          onEvent({ id: Number(msg.lastEventId), type, payload: JSON.parse(msg.data) as Record<string, unknown> });
        });
      }
      es.addEventListener("end", () => {
        es?.close();
        onEnd();
      });
      es.onopen = () => onConnection(true);
      es.onerror = () => {
        onConnection(false);
        if (es?.readyState === EventSource.CLOSED && !closed) retry();
      };
    });
  const retry = () =>
    setTimeout(() => {
      if (!closed) void open().catch(retry);
    }, 3000);
  void open().catch(() => {
    onConnection(false);
    retry();
  });
  return () => {
    closed = true;
    es?.close();
  };
}
