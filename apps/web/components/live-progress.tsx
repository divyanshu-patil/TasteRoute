import { useEffect, useRef } from "react";
import { CONTACT_STATUS, DRAFT_RESULT, STEP_DOING, STEP_LABEL } from "../lib/format";
import type { Progress } from "../lib/progress";

type Props = { progress: Progress; steps: string[]; title: string; onCancel?: () => void; cancelling?: boolean };

const resultLabel = (tool: string, result: string) => (tool === "draft_pitches" ? DRAFT_RESULT : CONTACT_STATUS)[result] ?? result;

export function LiveProgress({ progress, steps, title, onCancel, cancelling }: Props) {
  const state = (s: string) => (progress.done.includes(s) ? "done" : progress.active === s ? "active" : "todo");
  const log = useRef<HTMLUListElement>(null);
  useEffect(() => { // follow the newest line
    if (log.current) log.current.scrollTop = log.current.scrollHeight;
  }, [progress.log.length]);
  const outreach = progress.phase === "outreach";
  const checked = progress.counts.find_contacts;
  const found = progress.results.filter((r) => r.tool === "find_contacts" && r.result === "found").length;

  return (
    <section className="grid-2" aria-live="polite" aria-busy={!progress.finished}>
      <div className="card stack">
        <div className="row between">
          <h2 className="h2">{title}</h2>
          <div className="row" style={{ gap: 8 }}>
            <span className="tag">{progress.orchestration === "deterministic_fallback" ? "Deterministic plan" : "AI agent"}</span>
            {onCancel && <button className="btn-ghost btn-sm" disabled={cancelling} onClick={onCancel}>{cancelling ? "Cancelling…" : "Cancel"}</button>}
          </div>
        </div>
        <ol className="steps">
          {steps.map((s, i) => {
            const n = progress.counts[s];
            const now = progress.current?.tool === s ? progress.current.venue : null;
            return (
              <li key={s} data-state={state(s)}>
                <span className="step-ix" aria-hidden="true">{state(s) === "done" ? "✓" : String(i + 1).padStart(2, "0")}</span>
                <span>{STEP_LABEL[s]}</span>
                <span className="mono faint">{state(s) === "done" ? "done" : state(s) === "active" ? (n ? `${n.done} of ${n.of}` : <span className="dots">running</span>) : ""}</span>
                {state(s) === "active" && (
                  <div className="step-live">
                    <div className={`bar${n ? "" : " bar-busy"}`} role="progressbar" aria-label={STEP_LABEL[s]}
                      aria-valuemin={0} aria-valuemax={n?.of} aria-valuenow={n?.done}>
                      <span style={n ? { width: `${n.of ? (100 * n.done) / n.of : 0}%` } : undefined} />
                    </div>
                    {now && <span className="small muted dots">{STEP_DOING[s] ?? "Working on"} {now}</span>}
                  </div>
                )}
              </li>
            );
          })}
        </ol>
        {progress.results.length > 0 && (
          <ul className="live-results" aria-label="Results so far">
            {progress.results.slice(-6).reverse().map((r) => (
              <li key={r.id} className={r.result === "found" || r.result === "llm" ? "hit" : undefined}>
                <strong>{r.venue}</strong>
                <span className="small muted">{resultLabel(r.tool, r.result)}</span>
              </li>
            ))}
          </ul>
        )}
        {progress.warnings.map((w, i) => (
          <p key={i} className="banner banner-warn small">{w}</p>
        ))}
      </div>
      <div className="inverted stack">
        <div className="row between" style={{ alignItems: "flex-end" }}>
          {outreach ? (
            <>
              <div>
                <p className="mono" style={{ color: "#979797" }}>VENUES CHECKED</p>
                <p className="counter">{checked?.done ?? 0}<span style={{ color: "#979797", fontSize: "0.5em" }}>/{checked?.of ?? "–"}</span></p>
              </div>
              <p className="mono" style={{ textAlign: "right" }}>
                <span style={{ color: "#d1ffca" }}>{found} email{found === 1 ? "" : "s"} found</span>
                <br />
                <span style={{ color: "#fff100" }}>{progress.external} web lookups</span>
              </p>
            </>
          ) : (
            <>
              <div>
                <p className="mono" style={{ color: "#979797" }}>QLOO CALLS</p>
                <p className="counter" aria-label={`${progress.qlooLive} live Qloo calls, ${progress.qlooCached} cached`}>{progress.qlooLive + progress.qlooCached}</p>
              </div>
              <p className="mono" style={{ textAlign: "right" }}>
                <span style={{ color: "#fff100" }}>{progress.qlooLive} live</span>
                <br />
                <span style={{ color: "#d1ffca" }}>{progress.qlooCached} cached</span>
              </p>
            </>
          )}
        </div>
        <ul className="log" aria-label="Agent log" ref={log}>
          {progress.log.map((l, i) => (
            <li key={`${l.id}-${i}`}>
              <span className="k">{String(l.id).padStart(5, "0")}</span>
              <span className={l.kind === "done" ? "ok" : l.kind === "call" || l.kind === "warn" ? "hl" : undefined}>{l.text}</span>
            </li>
          ))}
          {!progress.log.length && <li><span className="k">…</span><span className="dots">Connecting to the run</span></li>}
        </ul>
      </div>
    </section>
  );
}
