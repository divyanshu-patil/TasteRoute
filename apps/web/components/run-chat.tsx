"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, apiStream, type S } from "../lib/api";
import { Markdown } from "../lib/markdown";

type Turn = S["AskTurn"];

/** One large four-point star and two small ones: the usual "AI" mark. */
function Sparkle({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" className="sparkle">
      <path d="M10 2c.5 4.2 2.8 6.5 7 7-4.2.5-6.5 2.8-7 7-.5-4.2-2.8-6.5-7-7 4.2-.5 6.5-2.8 7-7Z" />
      <path d="M18.5 13c.3 2.2 1.3 3.2 3.5 3.5-2.2.3-3.2 1.3-3.5 3.5-.3-2.2-1.3-3.2-3.5-3.5 2.2-.3 3.2-1.3 3.5-3.5Z" />
      <path d="M5 16.5c.2 1.4.8 2 2.2 2.2-1.4.2-2 .8-2.2 2.2-.2-1.4-.8-2-2.2-2.2 1.4-.2 2-.8 2.2-2.2Z" />
    </svg>
  );
}
const STARTERS = ["Which 3 venues should I visit first?", "Which product fits the most venues?", "Which high-confidence venues have the strongest lift?"];

/** A floating "Ask AI" chat about this run, answered only from its stored results (no Qloo or web calls). */
export function RunChat({ runId, raised = false }: { runId: string; raised?: boolean }) {
  const [open, setOpen] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [waited, setWaited] = useState(0);
  const [live, setLive] = useState<string | null>(null); // the answer as it streams in
  const stop = useRef<AbortController | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const log = useRef<HTMLOListElement>(null);

  useEffect(() => {
    if (!open) return;
    input.current?.focus();
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [open]);
  useEffect(() => {
    if (log.current) log.current.scrollTop = log.current.scrollHeight;
  }, [turns, busy, live]);
  useEffect(() => {
    if (!busy) return;
    setWaited(0);
    const t = window.setInterval(() => setWaited((n) => n + 1), 1000);
    return () => window.clearInterval(t);
  }, [busy]);
  const last = turns[turns.length - 1];

  const send = async (question: string) => {
    const text = question.trim();
    if (!text || busy) return;
    setBusy(true);
    setError(null);
    setQ("");
    const history = turns.slice(-6);
    setTurns((t) => [...t, { role: "user", content: text }]); // the question shows at once
    setLive("");
    let got = "";
    stop.current = new AbortController();
    try {
      await apiStream(`/v1/runs/${runId}/ask`, { question: text, history }, (d) => {
        got += d;
        setLive(got);
      }, stop.current.signal);
    } catch (e) {
      if (!stop.current.signal.aborted) setError(e instanceof ApiError ? e.detail || e.title : "Could not reach the assistant");
      if (!got) {
        setTurns((t) => t.slice(0, -1));
        setQ(text);
      }
    } finally {
      if (got) setTurns((t) => [...t, { role: "assistant", content: got }]);
      setLive(null);
      setBusy(false);
      stop.current = null;
    }
  };

  return (
    <div className={`chat-dock${raised ? " raised" : ""}`}>
      {open && (
        <section id="chat-panel" className="chat-panel stack-s" role="dialog" aria-labelledby="chat-h">
          <div className="stack-s" style={{ gap: 2 }}>
            <h2 id="chat-h" className="label row" style={{ gap: 6 }}><Sparkle size={14} />Ask AI about these results</h2>
            <span className="mono faint">Answers come only from this run&apos;s data · no new Qloo calls</span>
          </div>
          {turns.length > 0 ? (
            <ol ref={log} className="chat">
              {turns.map((t, i) => (
                <li key={i} className={t.role === "user" ? "chat-q" : "chat-a"}>
                  <span className="mono faint row" style={{ gap: 4 }}>{t.role === "user" ? "You" : <><Sparkle size={12} />TasteRoute</>}</span>
                  {t.role === "user" ? <p className="small">{t.content}</p> : <Markdown text={t.content} />}
                </li>
              ))}
              {busy && live ? (
                <li className="chat-a">
                  <span className="mono faint row" style={{ gap: 4 }}><Sparkle size={12} />TasteRoute</span>
                  <div className="chat-live"><Markdown text={live} /></div>
                </li>
              ) : busy && (
                <li className="chat-a">
                  <span className="mono faint row" style={{ gap: 4 }}><Sparkle size={12} />TasteRoute</span>
                  <span className="typing" aria-hidden="true"><i /><i /><i /></span>
                  <span className="mono faint">{waited < 5 ? "Reading your results…" : waited < 15 ? `Still working · ${waited}s` : `Long answer · ${waited}s, up to a minute`}</span>
                </li>
              )}
            </ol>
          ) : (
            <div className="row" style={{ gap: 6 }}>
              {STARTERS.map((s) => <button key={s} className="btn-ghost btn-sm" disabled={busy} onClick={() => send(s)}>{s}</button>)}
            </div>
          )}
          <p className="sr-only" aria-live="polite">{busy ? "TasteRoute is typing" : last?.role === "assistant" ? last.content : ""}</p>
          {error && <p className="small" role="alert" style={{ color: "var(--danger)" }}>{error}</p>}
          <form className="row" onSubmit={(e) => { e.preventDefault(); send(q); }}>
            <input ref={input} className="input" style={{ flex: 1, minWidth: 0 }} value={q} maxLength={500} onChange={(e) => setQ(e.target.value)}
              placeholder="Ask about venues, fit, products…" aria-label="Your question" />
            {busy
              ? <button type="button" className="btn" onClick={() => stop.current?.abort()}>Stop</button>
              : <button className="btn" disabled={!q.trim()}>Send</button>}
          </form>
        </section>
      )}
      <button className="btn chat-fab" aria-expanded={open} aria-controls="chat-panel" onClick={() => setOpen(!open)}>
        {open ? "Close" : <><Sparkle />Ask AI</>}
      </button>
    </div>
  );
}
