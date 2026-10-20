"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { LiveProgress } from "../../../../components/live-progress";
import { RunShell } from "../../../../components/run-shell";
import { Tour, type TourStep } from "../../../../components/tour";
import { Banner, ContactSource, EmptyState, NOTHING_SENT, Skeleton } from "../../../../components/ui";
import { forgetGoogle, googleToken, signIn, useAccount } from "../../../../lib/account";
import { ApiError, api, downloadCsv, type S } from "../../../../lib/api";
import { CONTACT_STATUS, OUTREACH_STEPS } from "../../../../lib/format";
import { cancelOutreach, sendAll, sendable, startingOutreach } from "../../../../lib/outreach";
import { useRun } from "../../../../lib/use-run";

type EditorProps = { draft: S["DraftOut"]; readOnly: boolean; onChange: (d: S["DraftOut"] | null) => void; onDirty: (id: string, dirty: boolean) => void };

function DraftEditor({ draft, readOnly, onChange, onDirty }: EditorProps) {
  const account = useAccount();
  const [subject, setSubject] = useState(draft.subject);
  const [body, setBody] = useState(draft.body);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const dirty = subject !== draft.subject || body !== draft.body;
  useEffect(() => { // Send all waits while any draft has unsaved edits
    onDirty(draft.id, dirty);
    return () => onDirty(draft.id, false);
  }, [draft.id, dirty, onDirty]);

  const save = async (status?: "approved") => {
    setBusy(true);
    setErr(null);
    try {
      onChange(await api<S["DraftOut"]>(`/v1/drafts/${draft.id}`, { method: "PATCH", body: { subject, body, ...(status ? { status } : {}) } }));
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail || e.title : "Could not save");
    } finally {
      setBusy(false);
    }
  };
  const approved = (draft.status === "approved" || draft.status === "exported") && !dirty;
  // Sends it from the user's own Gmail (F12). An unapproved draft is approved first, in the same click, and the button
  // says so; without sign-in or a fresh Google token, it goes to Google first
  const send = async () => {
    setBusy(true);
    setErr(null);
    try {
      if (dirty) await api(`/v1/drafts/${draft.id}`, { method: "PATCH", body: { subject, body } });
      const token = googleToken();
      if (!account.user || !token) return void (await signIn()); // back on this page; one more click sends
      if (!approved) await api(`/v1/drafts/${draft.id}`, { method: "PATCH", body: { subject, body, status: "approved" } });
      onChange(await api<S["DraftOut"]>(`/v1/drafts/${draft.id}/send`, { method: "POST", body: { google_access_token: token } }));
    } catch (e) {
      if (e instanceof ApiError && e.code === "gmail_reconnect") forgetGoogle();
      setErr(e instanceof ApiError ? e.detail || e.title : "Could not send");
    } finally {
      setBusy(false);
    }
  };
  const regenerate = async () => {
    setBusy(true);
    try {
      await api(`/v1/drafts/${draft.id}/regenerate`, { method: "POST" });
      onChange(null);
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail || e.title : "Could not regenerate");
      setBusy(false);
    }
  };
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(`To: ${draft.contact_email}\nSubject: ${subject}\n\n${body}`);
      setCopied(true);
    } catch {
      setErr("Copy failed. Select the text and copy it manually.");
    }
  };

  return (
    <article className="card draft" aria-labelledby={`d-${draft.id}`}>
      <div className="row between">
        <div className="stack-s" style={{ gap: 4 }}>
          <h3 id={`d-${draft.id}`} className="h3">{draft.venue_name}</h3>
          <span className="small">To <span className="email">{draft.contact_email}</span></span>
        </div>
        <div className="row" style={{ gap: 6 }}>
          <span className={`status status-${draft.status}`}>{draft.status}</span>
          <span className="tag tag-mist">{draft.source === "llm" ? `AI draft · ${draft.cited_evidence_ids.length} Qloo fact${draft.cited_evidence_ids.length === 1 ? "" : "s"} cited` : "template"}</span>
        </div>
      </div>
      <label className="field">
        <span>Subject</span>
        <input className="input" value={subject} maxLength={120} readOnly={readOnly} onChange={(e) => setSubject(e.target.value)} />
      </label>
      <label className="field">
        <span>Email</span>
        <textarea className="textarea" value={body} maxLength={4000} readOnly={readOnly} onChange={(e) => setBody(e.target.value)} />
      </label>
      {err && <p className="err" role="alert">{err}</p>}
      {draft.sent_at && <p className="small muted">Sent from your Gmail on {new Date(draft.sent_at).toLocaleString()}.</p>}
      {!readOnly && draft.status !== "sent" && (
        <div className="row between">
          <div className="row" style={{ gap: 8 }}>
            {dirty && <button className="btn-ghost btn-sm" disabled={busy} onClick={() => save()}>Save edits</button>}
            {draft.status !== "approved" && draft.status !== "exported" && (
              <button className="btn-ghost btn-sm" disabled={busy} onClick={regenerate}>Regenerate</button>
            )}
            <button className="btn-ghost btn-sm" onClick={copy}>{copied ? "Copied" : "Copy email"}</button>
          </div>
          <div className="row" style={{ gap: 8 }}>
            {draft.mailto && !dirty && <a className="btn-ghost btn-sm" href={draft.mailto}>Open in mail app</a>}
            {(draft.status === "draft" || draft.status === "edited" || dirty) && (
              <button className={account.user ? "btn-ghost btn-sm" : "btn btn-sm"} disabled={busy} onClick={() => save("approved")}>Approve</button>
            )}
            {account.enabled && (
              <button className="btn btn-sm" disabled={busy} onClick={send}>
                {!account.user ? "Log in to send with Gmail" : !googleToken() ? "Connect Gmail to send" : approved ? "Send with Gmail" : "Approve and send"}
              </button>
            )}
          </div>
        </div>
      )}
    </article>
  );
}

const TOUR: TourStep[] = [
  { target: "contacts", title: "Public business contacts", body: "Only addresses a venue published itself: its OpenStreetMap listing or its own website. Each shows where it was found and which sources were checked." },
  { target: "draft", title: "A grounded first email", body: "The AI writes from the venue's evidence only. A validator rejects names and numbers that aren't in it, claims like \"award-winning\" or \"already stocked\", and any taste claim that doesn't quote a Qloo fact; then it falls back to a template. You edit and approve it, then send it from your own Gmail or copy it out. Nothing goes without your click." },
  { target: "export", title: "Take it with you", body: "Download every venue, contact and approved draft as a CSV for your own mail app or CRM." },
];

export default function Outreach() {
  const { id } = useParams<{ id: string }>();
  const { run, error, progress, online, refresh } = useRun(id);
  const [contacts, setContacts] = useState<S["ContactStatusOut"][] | null>(null);
  const [drafts, setDrafts] = useState<S["DraftOut"][] | null>(null);
  const [version, setVersion] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const [starting, setStarting] = useState(() => !!startingOutreach(id)); // the results page sent the start just now
  const [cancelling, setCancelling] = useState(false);
  const account = useAccount();
  const [edited, setEdited] = useState<string[]>([]); // drafts with unsaved edits
  const onDirty = useCallback((draftId: string, dirty: boolean) =>
    setEdited((l) => (dirty ? (l.includes(draftId) ? l : [...l, draftId]) : l.filter((x) => x !== draftId))), []);
  const [confirming, setConfirming] = useState(false);
  const [sending, setSending] = useState<{ done: number; of: number } | null>(null);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    const start = startingOutreach(id);
    if (!start) return;
    let alive = true;
    start
      .then(() => alive && refresh())
      .catch((e: unknown) => {
        if (alive && (e as Error).name !== "AbortError") setErr(e instanceof ApiError ? e.detail || e.title : "Could not start outreach");
      })
      .finally(() => alive && setStarting(false));
    return () => {
      alive = false;
    };
  }, [id, refresh]);

  const cancel = async () => {
    setCancelling(true);
    try {
      await cancelOutreach(id);
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail || e.title : "Could not cancel");
    }
    setStarting(false);
    setCancelling(false);
    refresh();
  };

  const status = run?.status;
  useEffect(() => {
    if (!status) return;
    let alive = true;
    Promise.all([api<S["ContactStatusOut"][]>(`/v1/runs/${id}/contacts`), api<S["DraftOut"][]>(`/v1/runs/${id}/drafts`)])
      .then(([c, d]) => {
        if (!alive) return;
        setContacts(c);
        setDrafts(d);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [id, status, version, progress.results.length]); // and again as each venue finishes, so results show up live

  const running = starting || status === "outreach_running";
  const approved = (drafts ?? []).filter((d) => d.status === "approved" || d.status === "exported").length;
  const sent = (drafts ?? []).filter((d) => d.status === "sent").length;
  const unsent = sendable(drafts ?? []); // approved and not sent: all Send all may send
  const update = (d: S["DraftOut"] | null) => {
    if (d) setDrafts((list) => (list ?? []).map((x) => (x.id === d.id ? d : x)));
    else refresh();
  };
  // Send all (F12): every approved, unsent draft on this page, one at a time, after the user confirms the count
  const sendEvery = async () => {
    const token = googleToken();
    setConfirming(false);
    if (!account.user || !token) return void (await signIn()); // back here with Gmail connected
    setNote(null);
    setErr(null);
    setSending({ done: 0, of: unsent.length });
    const r = await sendAll(unsent, token, (done, d) => {
      if (d) update(d);
      setSending({ done, of: unsent.length });
    });
    setSending(null);
    if (r.reconnect) forgetGoogle();
    const text = [`Sent ${r.sent} email${r.sent === 1 ? "" : "s"} from your Gmail.`,
      r.reconnect ? "Gmail needs your permission again: click Send all to reconnect and send the rest." : "", ...r.failed];
    setNote({ ok: !r.reconnect && r.failed.length === 0, text: text.filter(Boolean).join(" ") });
  };
  const exportCsv = async () => {
    try {
      await downloadCsv(id);
      setVersion((v) => v + 1);
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail || e.title : "Export failed");
    }
  };

  return (
    <RunShell run={run} error={error} tab="outreach" online={online}>
      {running && <LiveProgress progress={progress} steps={OUTREACH_STEPS} title="Finding contacts and drafting" onCancel={cancel} cancelling={cancelling} />}
      <Banner tone="ink">{NOTHING_SENT}</Banner>
      {!!drafts?.length && !run?.is_demo && !(run?.brand.profile as { postal_address?: string } | undefined)?.postal_address && (
        <Banner tone="warn">Add your postal address before sending (required for commercial email in the US). It goes under your name in each email; set it in your brand details when you start a run.</Banner>
      )}
      {err && <Banner tone="warn">{err}</Banner>}
      {note && <Banner tone={note.ok ? "mint" : "warn"}>{note.text}</Banner>}
      {!running && status === "scouted" && run?.error_message && <Banner tone="warn">{run.error_message}</Banner>}
      {!contacts || contacts.length === 0 ? (
        running ? null : !contacts ? <Skeleton /> : ( // the live panel above covers the wait
          <EmptyState title="No venues selected yet">
            <p className="muted">Pick venues on the results page and choose “Find contacts &amp; draft”.</p>
            <Link className="btn" href={`/runs/${id}`}>Go to results</Link>
          </EmptyState>
        )
      ) : (
        <div className="split">
          <section className="card stack sticky" aria-labelledby="contacts-h" data-tour="contacts">
            <h2 id="contacts-h" className="h2">Contacts</h2>
            <ul className="stack-s" style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {contacts.map((c) => (
                <li key={c.venue_id} className="card-mist stack-s" style={{ padding: "14px 16px" }}>
                  <div className="row between"><strong>{c.rank}. {c.name}</strong></div>
                  {c.contacts[0] ? (
                    <span className="small"><span className="email">{c.contacts[0].email}</span> <span className="mono faint"><ContactSource contact={c.contacts[0]} />{c.contacts[0].role ? ` · ${c.contacts[0].role}` : ""}</span></span>
                  ) : (
                    <span className="small muted">{CONTACT_STATUS[c.status] ?? c.status}</span>
                  )}
                  <span className="mono faint">
                    checked:{" "}
                    {c.checked_sources.length ? c.checked_sources.map((s, i) => (
                      <span key={s}>
                        {i > 0 && ", "}
                        {s.includes("website") && c.website && /^https?:\/\//i.test(c.website)
                          ? <a className="link" href={c.website} target="_blank" rel="noopener noreferrer">{s} ↗</a>
                          : s}
                      </span>
                    )) : "–"}
                  </span>
                </li>
              ))}
            </ul>
          </section>
          <section className="stack" aria-label="Drafts" data-tour="draft">
            {(drafts ?? []).map((d) => (
              <DraftEditor key={`${d.id}-${d.updated_at}`} draft={d} readOnly={!!run?.is_demo} onChange={update} onDirty={onDirty} />
            ))}
            {drafts && drafts.length === 0 && !running && <EmptyState title="No drafts">Drafts are written only for venues with a public business email.</EmptyState>}
          </section>
        </div>
      )}
      {drafts && drafts.length > 0 && (
        <div className="actionbar" role="region" aria-label="Export" data-tour="export">
          <div>
            {sending ? (
              <span role="status">Sending {sending.done + 1 > sending.of ? sending.of : sending.done + 1} of {sending.of}…</span>
            ) : confirming ? (
              <span role="status">Send {unsent.length} approved draft{unsent.length === 1 ? "" : "s"} from your Gmail?</span>
            ) : (
              <span><strong>{approved}</strong> of {drafts.length} approved{sent > 0 && <>, <strong>{sent}</strong> sent</>}</span>
            )}
            <div className="row" style={{ gap: 8 }}>
              {account.enabled && !run?.is_demo && unsent.length > 0 && !sending && (confirming ? (
                <>
                  <button className="btn-ghost" onClick={() => setConfirming(false)}>Cancel</button>
                  <button className="btn" onClick={sendEvery}>Send {unsent.length}</button>
                </>
              ) : (
                <button className="btn" disabled={edited.length > 0} title={edited.length ? "Save or undo your edits first" : undefined}
                  onClick={() => (account.user && googleToken() ? setConfirming(true) : void signIn())}>
                  {!account.user ? "Log in to send all" : !googleToken() ? "Connect Gmail to send all" : edited.length ? "Save edits to send all" : `Send all approved (${unsent.length})`}
                </button>
              ))}
              {!confirming && !sending && <button className={account.user ? "btn-ghost" : "btn"} onClick={exportCsv}>Download CSV</button>}
            </div>
          </div>
        </div>
      )}
      <Tour steps={TOUR} ready={!!contacts && !!drafts} next={{ href: `/runs/${id}/trace?tour=1`, label: "See the trace" }} />
    </RunShell>
  );
}
