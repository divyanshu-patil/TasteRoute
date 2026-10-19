import type { Schemas } from "@repo/contracts";

export type S = Schemas;
export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
const KEY = "ss_ws";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    public title: string,
    public detail: string,
  ) {
    super(detail || title);
  }
}

function stored(): string | null {
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

function store(token: string): void {
  try {
    window.localStorage.setItem(KEY, token);
  } catch {
    // private mode: the token lives for this page only
  }
}

let pending: Promise<string> | null = null;
let memory: string | null = null;

/** Gets or creates the anonymous workspace token (signed by the API, kept in localStorage as ss_ws). */
export function workspaceToken(): Promise<string> {
  if (memory) return Promise.resolve(memory);
  pending ??= fetch(`${API_URL}/v1/workspaces/session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ workspace_token: stored() }),
  })
    .then(async (r) => {
      if (!r.ok) throw await toError(r);
      const body = (await r.json()) as S["SessionOut"];
      memory = body.workspace_token;
      store(memory);
      return memory;
    })
    .finally(() => {
      pending = null;
    });
  return pending;
}

async function toError(r: Response): Promise<ApiError> {
  try {
    const p = (await r.json()) as { code?: string; title?: string; detail?: string };
    return new ApiError(r.status, p.code ?? "error", p.title ?? r.statusText, p.detail ?? "");
  } catch {
    return new ApiError(r.status, "network_error", r.statusText || "Request failed", "");
  }
}

export async function api<T>(path: string, init: { method?: string; body?: unknown; signal?: AbortSignal } = {}): Promise<T> {
  const call = async (token: string) =>
    fetch(`${API_URL}${path}`, {
      method: init.method ?? "GET",
      headers: { "Content-Type": "application/json", "X-Workspace-Token": token },
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
      signal: init.signal,
    });
  let r: Response;
  try {
    r = await call(await workspaceToken());
    if (r.status === 401) {
      memory = null; // token expired or DB reset: start a fresh workspace once
      store("");
      r = await call(await workspaceToken());
    }
  } catch (e) {
    if (e instanceof ApiError || init.signal?.aborted) throw e;
    throw new ApiError(0, "network_error", "Can't reach the TasteRoute API", "Check your connection and try again.");
  }
  if (!r.ok) throw await toError(r);
  if (r.status === 204) return undefined as T;
  return (await r.json()) as T;
}

/** Downloads the CSV with the workspace header (a plain link can't send it). */
export async function downloadCsv(runId: string): Promise<void> {
  const r = await fetch(`${API_URL}/v1/runs/${runId}/export.csv`, { headers: { "X-Workspace-Token": await workspaceToken() } });
  if (!r.ok) throw await toError(r);
  const name = /filename="([^"]+)"/.exec(r.headers.get("content-disposition") ?? "")?.[1] ?? "tasteroute.csv";
  const url = URL.createObjectURL(await r.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  URL.revokeObjectURL(url);
}
