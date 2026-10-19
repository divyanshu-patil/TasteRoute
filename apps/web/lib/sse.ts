import { API_URL, workspaceToken } from "./api";

export type RunEvent = { id: number; type: string; payload: Record<string, unknown> };
export const EVENT_TYPES = [
  "phase_started", "tool_call", "step_done", "qloo_call", "external_call", "warning", "phase_done", "failed", "venue",
] as const;

/** EventSource with the token as a query param. The browser reconnects with Last-Event-ID; the API replays. */
export function subscribeRun(
  runId: string,
  onEvent: (e: RunEvent) => void,
  onEnd: () => void,
  onConnection: (online: boolean) => void,
): () => void {
  let es: EventSource | null = null;
  let closed = false;
  void workspaceToken().then((token) => {
    if (closed) return;
    es = new EventSource(`${API_URL}/v1/runs/${runId}/events?token=${encodeURIComponent(token)}`);
    for (const type of EVENT_TYPES) {
      es.addEventListener(type, (m) => {
        const msg = m as MessageEvent<string>;
        onEvent({ id: Number(msg.lastEventId), type, payload: JSON.parse(msg.data) as Record<string, unknown> });
      });
    }
    es.addEventListener("end", () => {
      es?.close();
      onEnd();
    });
    es.onopen = () => onConnection(true);
    es.onerror = () => onConnection(false);
  });
  return () => {
    closed = true;
    es?.close();
  };
}
