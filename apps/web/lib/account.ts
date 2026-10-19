import { createClient, type Session, type SupabaseClient } from "@supabase/supabase-js";
import { useEffect, useState } from "react";
import { api, setWorkspaceToken, workspaceToken, type S } from "./api";

// Sign-in (F12): Supabase Auth with Google. It keeps the workspace across devices, and asks for permission to send
// from the user's own Gmail. Google's token lasts an hour and goes only to our API, once per email sent.
const GMAIL_SEND = "https://www.googleapis.com/auth/gmail.send";
const GOOGLE = "tr_google"; // { token, exp }
const LINKED = "tr_linked"; // the account this browser's workspace is tied to

let client: SupabaseClient | null | undefined;
function supabase(): SupabaseClient | null {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (client === undefined) client = url && key ? createClient(url, key, { auth: { flowType: "pkce" } }) : null;
  return client;
}

const read = (k: string): string | null => {
  try {
    return window.localStorage.getItem(k);
  } catch {
    return null;
  }
};
const write = (k: string, v: string | null): void => {
  try {
    if (v === null) window.localStorage.removeItem(k);
    else window.localStorage.setItem(k, v);
  } catch {
    // private mode: signed in for this page only
  }
};

function google(): { token: string; exp: number } | null {
  try {
    return JSON.parse(read(GOOGLE) ?? "null") as { token: string; exp: number } | null;
  } catch {
    return null;
  }
}
/** The Google token for sending, while it is still valid. */
export function googleToken(): string | null {
  const g = google();
  return g && g.exp > Date.now() ? g.token : null;
}
/** Kept, marked expired: Supabase's saved session still holds the old token and would bring it back on reload. */
export function forgetGoogle(): void {
  const g = google();
  if (g) write(GOOGLE, JSON.stringify({ ...g, exp: 0 }));
}

/** Goes to Google and comes back to this page signed in, with Gmail sending allowed. */
export async function signIn(): Promise<void> {
  await supabase()?.auth.signInWithOAuth({ provider: "google", options: { redirectTo: window.location.href, scopes: GMAIL_SEND } });
}

export async function signOut(scope: "global" | "local" = "global"): Promise<void> {
  await supabase()?.auth.signOut({ scope }).catch(() => undefined);
  write(GOOGLE, null);
  write(LINKED, null);
  setWorkspaceToken(null); // the next request starts a new anonymous workspace
  window.location.assign("/");
}

/** Deletes the account and all its work at once (privacy policy), then signs out. */
export async function deleteAccount(): Promise<void> {
  await api("/v1/workspaces/me", { method: "DELETE" });
  await signOut("local"); // the Supabase user is already gone
}

let linking: Promise<void> | null = null;
/** Ties this browser's workspace to the account once; work done before signing in stays. */
function link(session: Session): Promise<void> {
  linking ??= (async () => {
    const before = await workspaceToken();
    const out = await api<S["AccountOut"]>("/v1/workspaces/login", {
      method: "POST",
      body: { access_token: session.access_token, workspace_token: before },
    });
    setWorkspaceToken(out.workspace_token);
    write(LINKED, session.user.id);
    if (out.workspace_token !== before) window.location.reload(); // the account's own runs
  })().finally(() => {
    linking = null;
  });
  return linking;
}

type Who = { email: string; name: string | null; avatar: string | null };

/** Who is signed in (null when not), with Google's name and picture, and whether sign-in is set up at all. */
export function useAccount(): { enabled: boolean; user: Who | null; error: string | null } {
  const [user, setUser] = useState<Who | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [enabled, setEnabled] = useState(false);
  useEffect(() => {
    const sb = supabase();
    if (!sb) return;
    setEnabled(true);
    const { data } = sb.auth.onAuthStateChange((_event, session) => {
      const u = session?.user;
      const meta = (u?.user_metadata ?? {}) as { full_name?: string; name?: string; avatar_url?: string; picture?: string };
      setUser(u?.email ? { email: u.email, name: meta.full_name ?? meta.name ?? null, avatar: meta.avatar_url ?? meta.picture ?? null } : null);
      if (!session) return;
      if (session.provider_token && session.provider_token !== google()?.token) {
        write(GOOGLE, JSON.stringify({ token: session.provider_token, exp: Date.now() + 55 * 60_000 })); // new: just signed in
      }
      if (read(LINKED) !== session.user.id) {
        // deferred: Supabase asks callbacks not to await its own calls
        setTimeout(() => link(session).catch((e: unknown) => setError(e instanceof Error ? e.message : "Sign-in failed")), 0);
      }
    });
    return () => data.subscription.unsubscribe();
  }, []);
  return { enabled, user, error };
}
