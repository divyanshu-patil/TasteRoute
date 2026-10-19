"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { LiveProgress } from "../../../components/live-progress";
import { ReasonText } from "../../../components/reason";
import { RunShell } from "../../../components/run-shell";
import { Banner, ConfidenceBadge, EmptyState, ErrorPanel, Skeleton, Tip } from "../../../components/ui";
import { ApiError, api, type S } from "../../../lib/api";
import { CONTACT_STATUS, FIT_LABEL, SCOUT_STEPS, liftText, pct, venueTypeLabel } from "../../../lib/format";
import { useRun } from "../../../lib/use-run";

const PAGE = 20;
const MAX_OUTREACH = 25;
const CONF_OK: Record<string, string[]> = { high: ["high"], medium: ["high", "medium"], low: ["high", "medium", "low"] };
const WEIGHTS = [
  { label: "Balanced", target: 0.7, lift: 0.3 },
  { label: "Taste first", target: 1, lift: 0 },
  { label: "Lift first", target: 0.4, lift: 0.6 },
];

export default function RunPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { run, error, progress, online, refresh } = useRun(id);
  const [page, setPage] = useState<S["VenuePage"] | null>(null);
  const [type, setType] = useState("");
  const [conf, setConf] = useState("");
  const [product, setProduct] = useState("");
  const [sort, setSort] = useState<"fit" | "lift">("fit");
  const [shown, setShown] = useState(PAGE);
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const ready = run && ["scouted", "done", "outreach_running"].includes(run.status);
  useEffect(() => {
    if (!ready) return;
    let alive = true;
    api<S["VenuePage"]>(`/v1/runs/${id}/venues?limit=100`).then((p) => alive && setPage(p)).catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [id, ready]);

  const rows = useMemo(() => {
    const items = (page?.items ?? []).filter(
      (v) =>
        (!type || v.venue_type === type) &&
        (!conf || (CONF_OK[conf] ?? []).includes(v.confidence)) &&
        (!product || v.best_product?.product_id === product),
    );
    return sort === "lift" ? [...items].sort((a, b) => b.lift - a.lift || a.rank - b.rank) : items;
  }, [page, type, conf, product, sort]);

  const toggle = (vid: string) => setSelected((s) => (s.includes(vid) ? s.filter((x) => x !== vid) : s.length >= MAX_OUTREACH ? s : [...s, vid]));

  const findContacts = async () => {
    setBusy(true);
    setActionError(null);
    try {
      await api(`/v1/runs/${id}/contacts`, { method: "POST", body: { venue_ids: selected } });
      router.push(`/runs/${id}/outreach`);
    } catch (e) {
      setActionError(e instanceof ApiError ? e.detail || e.title : "Could not start outreach");
      setBusy(false);
    }
  };

  const rescore = async (w: (typeof WEIGHTS)[number]) => {
    try {
      setPage(await api<S["VenuePage"]>(`/v1/runs/${id}/rescore`, { method: "POST", body: { target: w.target, lift: w.lift } }));
      refresh();
    } catch (e) {
      setActionError(e instanceof ApiError ? e.detail || e.title : "Could not rescore");
    }
  };

  const retry = async () => {
    if (!run) return;
    try {
      const out = await api<S["RunCreated"]>("/v1/runs", {
        method: "POST",
        body: { brand_id: run.brand.id, product_ids: run.products.map((p) => p.id), city: run.city, venue_types: run.venue_types },
      });
      router.push(`/runs/${out.run_id}`);
    } catch (e) {
      setActionError(e instanceof ApiError ? e.detail || e.title : "Could not retry");
    }
  };

  const counters = run?.counters as Record<string, number> | undefined;
  const items = page?.items ?? [];
  const hasFilters = !!(type || conf || product);
  const signal = Object.values((run?.resolution ?? {}) as Record<string, { entities: string[] }>).flatMap((r) => r.entities);

  return (
    <RunShell run={run} error={error} tab="results" online={online}>
      {run && ["pending", "running"].includes(run.status) && <LiveProgress progress={progress} steps={SCOUT_STEPS} title="Ranking venues" />}

      {run?.status === "failed" && (
        <ErrorPanel code={run.error_code ?? undefined} title={run.error_code?.startsWith("qloo") ? "Qloo is unavailable" : "This run stopped"}>
          <p style={{ maxWidth: "60ch" }}>
            {run.error_message}{" "}
            {run.error_code?.startsWith("qloo") && "TasteRoute never ranks venues without Qloo, so nothing partial is shown."}
          </p>
          {!run.is_demo && <div className="row"><button className="btn" onClick={retry}>Retry run</button><Link className="btn-ghost" href="/start">Change inputs</Link></div>}
        </ErrorPanel>
      )}

      {ready && (
        <>
          <section className="grid-4" aria-label="Run summary">
            <div className="stat">
              <span className="label"><Tip label="Venues ranked">Venues Qloo scored for your taste in this city, across the venue types you picked.</Tip></span>
              <span className="v">{page?.total ?? "–"}</span>
            </div>
            <div className="stat">
              <span className="label"><Tip label="High confidence">Top 20% taste fit, clearly above a typical venue, backed by at least two of your reference brands (or by your own brand when Qloo knows it and it is the only one).</Tip></span>
              <span className="v">{items.filter((v) => v.confidence === "high").length}</span>
            </div>
            <div className="stat">
              <span className="label"><Tip label="Qloo calls">Qloo API requests this run made. Cached calls reuse a stored answer and cost nothing.</Tip></span>
              <span className="v">{(counters?.qloo_live ?? 0) + (counters?.qloo_cached ?? 0)}</span>
              <span className="mono faint">{counters?.qloo_live ?? 0} live · {counters?.qloo_cached ?? 0} cached</span>
            </div>
            <div className="stat" style={{ background: "#000", color: "#fff" }}>
              <span className="label" style={{ color: "#979797" }}>Orchestration</span>
              <span className="h3">{run.orchestration === "agent" ? "AI agent" : "Deterministic plan"}</span>
              <span className="mono" style={{ color: "#979797" }}>{run.orchestration_reason ?? "tool calls checked by a plan guard"}</span>
            </div>
          </section>

          {signal.length > 0 && (
            <div className="row">
              <span className="mono muted">TASTE SIGNAL FROM QLOO</span>
              {[...new Set(signal)].map((s) => <span key={s} className="tag">{s}</span>)}
            </div>
          )}

          {(page?.warnings ?? run.warnings).map((w) => <Banner key={w} tone="warn">{w}</Banner>)}
          {run.orchestration === "deterministic_fallback" && run.orchestration_reason?.includes("LLM") && (
            <Banner>The AI agent was unavailable, so the fixed plan ran the same Qloo steps. Rankings are identical; drafts may use templates.</Banner>
          )}
          {actionError && <Banner tone="warn">{actionError}</Banner>}

          <section className="card stack" aria-label="Filters">
            <div className="row between">
              <div className="row">
                <label className="field" style={{ minWidth: 150 }}>
                  <span>Venue type</span>
                  <select className="select" value={type} onChange={(e) => { setType(e.target.value); setShown(PAGE); }}>
                    <option value="">All types</option>
                    {run.venue_types.map((t) => <option key={t} value={t}>{venueTypeLabel(t)}</option>)}
                  </select>
                </label>
                <label className="field" style={{ minWidth: 150 }}>
                  <span>Confidence</span>
                  <select className="select" value={conf} onChange={(e) => { setConf(e.target.value); setShown(PAGE); }}>
                    <option value="">Any</option>
                    <option value="high">High only</option>
                    <option value="medium">Medium or high</option>
                  </select>
                </label>
                <label className="field" style={{ minWidth: 170 }}>
                  <span>Best product</span>
                  <select className="select" value={product} onChange={(e) => { setProduct(e.target.value); setShown(PAGE); }}>
                    <option value="">Any product</option>
                    {run.products.map((p) => <option key={p.id as string} value={p.id as string}>{p.name as string}</option>)}
                  </select>
                </label>
                <label className="field" style={{ minWidth: 130 }}>
                  <span>Sort by</span>
                  <select className="select" value={sort} onChange={(e) => setSort(e.target.value as "fit" | "lift")}>
                    <option value="fit">Fit</option>
                    <option value="lift">Lift</option>
                  </select>
                </label>
              </div>
              {!run.is_demo && (
                <div className="stack-s">
                  <span className="label">Weighting (no new Qloo calls)</span>
                  <div className="row" style={{ gap: 6 }}>
                    {WEIGHTS.map((w) => (
                      <button key={w.label} className="btn-ghost btn-sm" aria-pressed={run.weights.target === w.target && run.weights.lift === w.lift} onClick={() => rescore(w)}
                        style={run.weights.target === w.target && run.weights.lift === w.lift ? { background: "#000", color: "#fff", borderColor: "#000" } : undefined}>
                        {w.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </section>

          {!page ? (
            <Skeleton rows={10} />
          ) : rows.length === 0 ? (
            <EmptyState title={hasFilters ? "No venues match these filters" : "No venues"}>
              {hasFilters && <button className="btn-ghost" onClick={() => { setType(""); setConf(""); setProduct(""); }}>Clear filters</button>}
            </EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="t">
                <caption className="sr-only">Venues ranked by taste fit</caption>
                <thead>
                  <tr>
                    {!run.is_demo && <th scope="col"><span className="sr-only">Select</span></th>}
                    <th scope="col">#</th>
                    <th scope="col">Venue</th>
                    <th scope="col"><Tip label="Fit">0–100. 70% how strongly the venue&apos;s guests share your taste (Qloo affinity percentile), 30% how far that beats a popularity-only baseline.</Tip></th>
                    <th scope="col"><Tip label="Lift">How much higher this venue ranks for your taste than for plain popularity. Positive means a real taste match, not just a busy place.</Tip></th>
                    <th scope="col">Confidence</th>
                    <th scope="col">Best product</th>
                    <th scope="col">Why</th>
                    <th scope="col">Contact</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.slice(0, shown).map((v) => {
                    const sel = selected.includes(v.venue_id);
                    return (
                      <tr key={v.venue_id} className={sel ? "selected" : undefined}>
                        {!run.is_demo && (
                          <td>
                            <input type="checkbox" className="check" style={{ width: 20, height: 20, accentColor: "#000" }} checked={sel} onChange={() => toggle(v.venue_id)} aria-label={`Select ${v.name}`} />
                          </td>
                        )}
                        <td><span className="rank">{v.rank}</span></td>
                        <td className="cell-wide">
                          <Link className="venue-name" href={`/runs/${id}/venues/${v.venue_id}`}>{v.name}</Link>
                          <div className="mono faint">{venueTypeLabel(v.venue_type)}{v.neighborhood ? ` · ${v.neighborhood}` : ""}</div>
                        </td>
                        <td data-label="Fit" className="num">
                          <span className="score">{pct(v.fit)}</span>
                          <div className="fitbar" aria-hidden="true"><span style={{ width: `${pct(v.fit)}%` }} /></div>
                        </td>
                        <td data-label="Lift">
                          <Tip label={<span className={v.lift > 0.005 ? "lift-up" : "lift-flat"}>{liftText(v.lift)}</span>}>
                            {`Taste percentile ${pct(v.target_pct)} vs popularity percentile ${pct(v.baseline_pct)}.`}
                          </Tip>
                        </td>
                        <td data-label="Confidence"><ConfidenceBadge level={v.confidence} /></td>
                        <td data-label="Best product">
                          {v.best_product ? (
                            <>
                              <div style={{ fontWeight: 500 }}>{v.best_product.name}</div>
                              <div className="mono faint">{FIT_LABEL[v.best_product.label ?? ""] ?? ""}</div>
                            </>
                          ) : <span className="faint">–</span>}
                        </td>
                        <td data-label="Why" className="cell-wide">
                          <details className="reason small">
                            <summary><span className="clamp">{v.reason}</span></summary>
                            <p style={{ marginTop: 8 }}><ReasonText text={v.reason ?? ""} traceHref={`/runs/${id}/trace`} /></p>
                            <Link className="link small" href={`/runs/${id}/venues/${v.venue_id}`}>{v.evidence_count} evidence items →</Link>
                          </details>
                        </td>
                        <td data-label="Contact" className="small muted">{CONTACT_STATUS[v.contact_status] ?? v.contact_status}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {shown < rows.length && (
                <div className="row" style={{ justifyContent: "center", padding: 16 }}>
                  <button className="btn-ghost" onClick={() => setShown(shown + PAGE)}>Show {Math.min(PAGE, rows.length - shown)} more</button>
                </div>
              )}
            </div>
          )}

          {!run.is_demo && selected.length > 0 && (
            <div className="actionbar" role="region" aria-label="Selection">
              <div>
                <span><strong>{selected.length}</strong> selected{selected.length >= MAX_OUTREACH ? " (max)" : ""}</span>
                <div className="row" style={{ gap: 8 }}>
                  <button className="link" style={{ color: "#979797" }} onClick={() => setSelected([])}>Clear</button>
                  <button className="btn" disabled={busy || run.status === "outreach_running"} onClick={findContacts}>
                    {busy ? "Starting…" : "Find contacts & draft →"}
                  </button>
                </div>
              </div>
            </div>
          )}
          {run.is_demo && (
            <div className="row">
              <Link className="btn" href={`/runs/${id}/outreach`}>See contacts and drafts →</Link>
              <Link className="btn-ghost" href={`/runs/${id}/trace`}>Open the trace</Link>
            </div>
          )}
        </>
      )}
    </RunShell>
  );
}
