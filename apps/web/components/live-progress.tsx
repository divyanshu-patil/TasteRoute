import { STEP_LABEL } from "../lib/format";
import type { Progress } from "../lib/progress";

export function LiveProgress({ progress, steps, title }: { progress: Progress; steps: string[]; title: string }) {
  const state = (s: string) => (progress.done.includes(s) ? "done" : progress.active === s ? "active" : "todo");
  return (
    <section className="grid-2" aria-live="polite">
      <div className="card stack">
        <div className="row between">
          <h2 className="h2">{title}</h2>
          <span className="tag">{progress.orchestration === "deterministic_fallback" ? "Deterministic plan" : "AI agent"}</span>
        </div>
        <ol className="steps">
          {steps.map((s, i) => (
            <li key={s} data-state={state(s)}>
              <span className="step-ix" aria-hidden="true">{state(s) === "done" ? "✓" : String(i + 1).padStart(2, "0")}</span>
              <span>{STEP_LABEL[s]}</span>
              <span className="mono faint">{state(s) === "done" ? "done" : state(s) === "active" ? "running" : ""}</span>
            </li>
          ))}
        </ol>
        {progress.warnings.map((w, i) => (
          <p key={i} className="banner banner-warn small">{w}</p>
        ))}
      </div>
      <div className="inverted stack">
        <div className="row between" style={{ alignItems: "flex-end" }}>
          <div>
            <p className="mono" style={{ color: "#979797" }}>QLOO CALLS</p>
            <p className="counter" aria-label={`${progress.qlooLive} live Qloo calls, ${progress.qlooCached} cached`}>{progress.qlooLive + progress.qlooCached}</p>
          </div>
          <p className="mono" style={{ textAlign: "right" }}>
            <span style={{ color: "#fff100" }}>{progress.qlooLive} live</span>
            <br />
            <span style={{ color: "#d1ffca" }}>{progress.qlooCached} cached</span>
          </p>
        </div>
        <ul className="log" aria-label="Agent log">
          {progress.log.map((l, i) => (
            <li key={`${l.id}-${i}`}>
              <span className="k">{String(l.id).padStart(5, "0")}</span>
              <span className={l.kind === "done" ? "ok" : l.kind === "call" || l.kind === "warn" ? "hl" : undefined}>{l.text}</span>
            </li>
          ))}
          {!progress.log.length && <li><span className="k">…</span><span>Connecting to the run…</span></li>}
        </ul>
      </div>
    </section>
  );
}
