"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { LiveProgress } from "../../../components/live-progress";
import { ReasonText } from "../../../components/reason";
import { RunShell } from "../../../components/run-shell";
import { Tour, type TourStep } from "../../../components/tour";
import { Banner, ConfidenceBadge, EmptyState, ErrorPanel, Skeleton, Tip } from "../../../components/ui";
import { VenueMap, type Pin } from "../../../components/venue-map";
import { ApiError, api, type S } from "../../../lib/api";
import { CONTACT_STATUS, FIT_LABEL, FIT_TIP, FLAG_CHIP, LIFT_TIP_MASS, SCOUT_STEPS, km, kmText, liftText, pct, venueTypeLabel } from "../../../lib/format";
import { cancelOutreach, startOutreach, startingOutreach } from "../../../lib/outreach";
import { useRun } from "../../../lib/use-run";

const PAGE = 20;
const MAX_OUTREACH = 25;
const CONF_OK: Record<string, string[]> = { high: ["high"], medium: ["high", "medium"], low: ["high", "medium", "low"] };
const WEIGHTS = [
  { label: "Balanced", target: 0.7, lift: 0.3 },
  { label: "Taste first", target: 1, lift: 0 },
  { label: "Lift first", target: 0.4, lift: 0.6 },
];
const TOUR: TourStep[] = [
  { target: "run-head", title: "A finished run", body: "The brand, its city and the venue types it covers. The sample is a fictional Brooklyn drinks maker; every number comes from real, stored Qloo calls." },
  { target: "stats", title: "What the run did", body: "How many venues Qloo scored, how many are high confidence, and the Qloo calls it took. Cached calls reuse a stored answer." },
  { target: "signal", title: "The taste signal", body: "Qloo matched each product to brands it knows, or to real comparable brands when a product is too new. Venues rank by how much their guests share these brands' fans' taste." },
  { target: "map", title: "Where they are", body: "Every ranked venue. The top 10 are numbered by rank, venues you select turn yellow, and the mint pin is your business, if you set one. Open a pin for its scores and distance." },
  { target: "table", title: "Fit and lift", body: "Fit is 70% taste (Qloo affinity percentile for your brands) and 30% lift. Lift compares the same venues under mass-market brands like Coca-Cola and Starbucks, so a venue doesn't rank high just because everyone likes it. Chains are hidden unless you show them." },
  { target: "route", title: "A route for the week", body: "The top 15 grouped into walkable areas, strongest taste hotspot first. The shading is Qloo's heatmap: where your brands' fans concentrate more than mass-market brands' fans. The ranking doesn't change." },
  { target: "llm", title: "Next to an LLM", body: "An LLM ranked the same venues from their names, types and neighbourhoods only. \"Only TasteRoute ranks this high\" marks venues in our top 15 that the LLM put below 30. On real stockists the two tied; the link shows the test." },
  { target: "reason", title: "Why each venue", body: "Open a reason to see what Qloo said and what is our inference. Each label links to the call in the trace." },
  { target: "weights", title: "Re-weight for free", body: "Shift the balance between taste and lift. Scores are recomputed from stored answers, with no new Qloo calls." },
];

export default function RunPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { run, error, progress, online, refresh } = useRun(id);
  const [page, setPage] = useState<S["VenuePage"] | null>(null);
  const [type, setType] = useState("");
  const [conf, setConf] = useState("");
  const [product, setProduct] = useState("");
  const [sort, setSort] = useState<"fit" | "lift" | "near">("fit");
  const [shown, setShown] = useState(PAGE);
  const [selected, setSelected] = useState<string[]>([]);
  const [actionError, setActionError] = useState<string | null>(null);
  const [showHidden, setShowHidden] = useState(false);
  const [llmBusy, setLlmBusy] = useState(false);
  const [pageError, setPageError] = useState<ApiError | null>(null);
  const [route, setRoute] = useState<S["RouteOut"] | null>(null);
  const [routeBusy, setRouteBusy] = useState(false);
  const [showHeat, setShowHeat] = useState(true);
  const [attempt, setAttempt] = useState(0);

  const ready = run && ["scouted", "done", "outreach_running"].includes(run.status);
  useEffect(() => {
    if (!ready) return;
    let alive = true;
    setPageError(null);
    api<S["VenuePage"]>(`/v1/runs/${id}/venues?limit=100${showHidden ? "&show_hidden=true" : ""}`)
      .then((p) => alive && setPage(p))
      .catch((e: unknown) => alive && setPageError(e instanceof ApiError ? e : new ApiError(0, "network", "Can't reach the TasteRoute API", "")));
    return () => {
      alive = false;
    };
  }, [id, ready, showHidden, attempt]);
  useEffect(() => {
    if (!ready) return;
    let alive = true;
    api<S["RouteOut"] | null>(`/v1/runs/${id}/route`).then((r) => alive && setRoute(r)).catch(() => undefined); // optional extra
    return () => {
      alive = false;
    };
  }, [id, ready]);

  const base = run?.base ?? null;
  const away = useCallback(
    (v: { lat?: number | null; lon?: number | null }) => (base && v.lat != null && v.lon != null ? km(base, { lat: v.lat, lon: v.lon }) : Infinity),
    [base],
  );
  const rows = useMemo(() => {
    const items = (page?.items ?? []).filter(
      (v) =>
        (!type || v.venue_type === type) &&
        (!conf || (CONF_OK[conf] ?? []).includes(v.confidence)) &&
        (!product || v.best_product?.product_id === product),
    );
    if (sort === "lift") return [...items].sort((a, b) => b.lift - a.lift || a.rank - b.rank);
    if (sort === "near" && base) return [...items].sort((a, b) => away(a) - away(b) || a.rank - b.rank);
    return items;
  }, [page, type, conf, product, sort, base, away]);

  const toggle = (vid: string) => setSelected((s) => (s.includes(vid) ? s.filter((x) => x !== vid) : s.length >= MAX_OUTREACH ? s : [...s, vid]));
  const visible = rows.slice(0, shown).map((v) => v.venue_id);
  const allShown = visible.length > 0 && visible.every((v) => selected.includes(v));
  const toggleShown = () =>
    setSelected((s) => (allShown ? s.filter((x) => !visible.includes(x)) : [...s, ...visible.filter((x) => !s.includes(x))].slice(0, MAX_OUTREACH)));

  // The outreach page opens at once and shows the start request; it can cancel it there too
  const findContacts = () => {
    startOutreach(id, selected);
    router.push(`/runs/${id}/outreach`);
  };
  const cancel = () => {
    setSelected([]);
    if (run?.status === "outreach_running" || startingOutreach(id)) {
      cancelOutreach(id).then(refresh, (e: unknown) => setActionError(e instanceof ApiError ? e.detail || e.title : "Could not cancel"));
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

  const compareLlm = async () => {
    setLlmBusy(true);
    try {
      setPage(await api<S["VenuePage"]>(`/v1/runs/${id}/llm-ranking`, { method: "POST" }));
      setShowHidden(false);
    } catch (e) {
      setActionError(e instanceof ApiError ? e.detail || e.title : "Could not get the LLM ranking");
    } finally {
      setLlmBusy(false);
    }
  };

  const planRoute = async () => {
    setRouteBusy(true);
    try {
      setRoute(await api<S["RouteOut"]>(`/v1/runs/${id}/route`, { method: "POST" }));
    } catch (e) {
      setActionError(e instanceof ApiError ? e.detail || e.title : "Could not plan the route");
    } finally {
      setRouteBusy(false);
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
  const mass = items.some((v) => v.popularity_pct != null);
  const hidden = page?.hidden ?? {};
  const nHidden = (hidden.chain ?? 0) + (hidden.signal_brand_venue ?? 0);
  const llm = items.some((v) => v.llm_rank != null);
  const hasFilters = !!(type || conf || product);
  const signal = Object.values((run?.resolution ?? {}) as Record<string, { entities: string[] }>).flatMap((r) => r.entities);
  const pins = useMemo<Pin[]>(
    () => rows.filter((v) => v.lat != null && v.lon != null).map((v): Pin => ({
      id: v.venue_id, lat: v.lat as number, lon: v.lon as number, label: String(v.rank), title: `${v.rank}. ${v.name}`,
      on: selected.includes(v.venue_id), dot: v.rank > 10 && !selected.includes(v.venue_id),
      sub: `${venueTypeLabel(v.venue_type)} · fit ${pct(v.fit)} · ${liftText(v.lift, v.popularity_pct != null)}${base ? ` · ${kmText(away(v))} from you` : ""}`,
      href: `/runs/${id}/venues/${v.venue_id}`,
    })).concat(base ? [{ id: "base", lat: base.lat, lon: base.lon, label: "You", title: base.label, sub: base.detail, base: true }] : []),
    [rows, selected, id, base, away],
  );
  const routePath = useMemo(() => route?.areas.map((a) => a.stops.map((x) => [x.lat, x.lon])), [route]);

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
          <section className="grid-4" aria-label="Run summary" data-tour="stats">
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
              <span className="mono" style={{ color: "#979797" }}>{run.orchestration_reason ?? (run.orchestration === "agent" ? "An AI agent chose each step; a rule checker approved every call" : "The same steps and rules, without the AI agent")}</span>
            </div>
          </section>

          {signal.length > 0 && (
            <div className="row" data-tour="signal">
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
                  <select className="select" value={sort} onChange={(e) => setSort(e.target.value as "fit" | "lift" | "near")}>
                    <option value="fit">Fit</option>
                    <option value="lift">Lift</option>
                    {base && <option value="near">Nearest to you</option>}
                  </select>
                </label>
                {(nHidden > 0 || showHidden) && (
                  <button className="btn-ghost btn-sm" aria-pressed={showHidden} onClick={() => { setShowHidden(!showHidden); setShown(PAGE); }}>
                    {showHidden ? "Hide chains" : `Show chains (${hidden.chain ?? 0})${hidden.signal_brand_venue ? ` and brands you resemble (${hidden.signal_brand_venue})` : ""}`}
                  </button>
                )}
                {!llm && !run.is_demo && (
                  <button className="btn-ghost btn-sm" onClick={compareLlm} disabled={llmBusy} aria-busy={llmBusy}>
                    {llmBusy ? "Asking the LLM…" : "Compare with an LLM"}
                  </button>
                )}
              </div>
              {!run.is_demo && (
                <div className="stack-s" data-tour="weights">
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

          {pins.length > 0 && (
            <section className="card stack-s" aria-labelledby="map-h" data-tour="map">
              <div className="row between">
                <h2 id="map-h" className="label">Map</h2>
                <span className="mono faint">{pins.length - (base ? 1 : 0)} venues · top 10 and your picks numbered{base ? " · You = your business" : ""}</span>
              </div>
              <VenueMap pins={pins} label="Map of the ranked venues" height={480} heat={route && showHeat ? route.heat : undefined} path={routePath} />
            </section>
          )}

          {(route || !run.is_demo) && (
            <section className="card stack-s" aria-labelledby="route-h" data-tour="route">
              <div className="row between">
                <h2 id="route-h" className="label">Taste route</h2>
                {route && (
                  <label className="row small" style={{ gap: 6 }}>
                    <input type="checkbox" checked={showHeat} onChange={(e) => setShowHeat(e.target.checked)} /> Taste heatmap on the map
                  </label>
                )}
              </div>
              {route ? (
                <>
                  <p className="small muted" style={{ maxWidth: "75ch" }}>
                    The top {route.areas.reduce((n, a) => n + a.stops.length, 0)} grouped into walkable areas, strongest taste hotspot first: where Qloo&apos;s heatmap shows
                    your brands&apos; fans concentrating more than mass-market brands&apos; fans (shaded on the map, darker is stronger). One area per visit; the dashed lines are its walk, in straight lines. The ranking doesn&apos;t change.
                  </p>
                  <ol className="route">
                    {route.areas.map((a) => (
                      <li key={a.stops[0]?.venue_id ?? a.name}>
                        <div className="row between">
                          <strong>{a.name}</strong>
                          <span className="mono faint">
                            <Tip label={`${a.lift > 0 ? "+" : ""}${a.lift} hotspot`}>Qloo heatmap at these venues: your brands&apos; affinity rank minus mass-market brands&apos;, in percentile points.</Tip>
                            {" · "}{a.stops.length} {a.stops.length === 1 ? "venue" : "venues"}{a.walk_km ? ` · ${a.walk_km} km walk` : ""}
                          </span>
                        </div>
                        <span className="small">
                          {a.stops.map((x, i) => (
                            <span key={x.venue_id}>{i > 0 && " → "}<Link className="link" href={`/runs/${id}/venues/${x.venue_id}`}>{x.name}</Link> <span className="mono faint">#{x.rank}</span></span>
                          ))}
                        </span>
                      </li>
                    ))}
                  </ol>
                </>
              ) : (
                <div className="row between">
                  <p className="small muted">Group the top 15 into walkable areas, ordered by Qloo&apos;s taste heatmap. Two Qloo calls; the ranking doesn&apos;t change.</p>
                  <button className="btn-ghost btn-sm" onClick={planRoute} disabled={routeBusy} aria-busy={routeBusy}>{routeBusy ? "Planning…" : "Plan a taste route"}</button>
                </div>
              )}
            </section>
          )}

          {llm && (
            <p className="small muted" data-tour="llm">
              LLM rank: an LLM&apos;s ranking from names, types and neighbourhoods only, for comparison. It never changes
              fit. <Link className="link" href="/evaluation">How the two did on real accounts</Link>
            </p>
          )}

          {pageError && !page ? (
            <ErrorPanel code={pageError.code} title={pageError.status === 0 ? "Can't reach the TasteRoute API" : "Couldn't load the venues"}>
              <p className="muted">{pageError.detail || "Check your connection and try again."}</p>
              <div className="row"><button className="btn" onClick={() => setAttempt(attempt + 1)}>Retry</button></div>
            </ErrorPanel>
          ) : !page ? (
            <Skeleton rows={10} />
          ) : rows.length === 0 ? (
            <EmptyState title={hasFilters ? "No venues match these filters" : "No venues"}>
              {hasFilters && <button className="btn-ghost" onClick={() => { setType(""); setConf(""); setProduct(""); }}>Clear filters</button>}
            </EmptyState>
          ) : (
            <div className="table-wrap" data-tour="table">
              {!run.is_demo && (
                <div className="row select-all" style={{ padding: "14px 16px 0" }}>
                  <label className="check small">
                    <input type="checkbox" checked={allShown} onChange={toggleShown} />
                    Select all shown{visible.length > MAX_OUTREACH ? ` (first ${MAX_OUTREACH})` : ""}
                  </label>
                </div>
              )}
              <table className="t">
                <caption className="sr-only">Venues ranked by taste fit</caption>
                <thead>
                  <tr>
                    {!run.is_demo && (
                      <th scope="col">
                        <input type="checkbox" className="check" style={{ width: 20, height: 20, accentColor: "#000" }} checked={allShown} onChange={toggleShown}
                          aria-label={`Select all ${visible.length} shown${visible.length > MAX_OUTREACH ? ` (first ${MAX_OUTREACH})` : ""}`} title="Select all shown" />
                      </th>
                    )}
                    <th scope="col">#</th>
                    <th scope="col">Venue</th>
                    <th scope="col"><Tip label="Fit">{mass ? "0–100. 70% how strongly the venue's guests share your taste (Qloo affinity percentile), 30% how far that beats their taste for mass-market brands." : "0–100. 70% how strongly the venue's guests share your taste (Qloo affinity percentile), 30% how far that beats a popularity-only baseline."}</Tip></th>
                    <th scope="col"><Tip label="Lift">{mass ? LIFT_TIP_MASS : "How much higher this venue ranks for your taste than for plain popularity. Positive means a real taste match, not just a busy place."}</Tip></th>
                    <th scope="col">Confidence</th>
                    <th scope="col">Best product</th>
                    <th scope="col">Why</th>
                    <th scope="col">Contact</th>
                    {llm && <th scope="col" className="num"><Tip label="LLM rank">An LLM ranked the same venues from their names, types and neighbourhoods only, with your products and reference brands. For comparison; it never changes fit.</Tip></th>}
                  </tr>
                </thead>
                <tbody>
                  {rows.slice(0, shown).map((v, i) => {
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
                          <div className="mono faint">{venueTypeLabel(v.venue_type)}{v.neighborhood ? ` · ${v.neighborhood}` : ""}{base && away(v) < Infinity ? ` · ${kmText(away(v))}` : ""}</div>
                          {v.flags.some((f) => FLAG_CHIP[f]) && (
                            <div className="row" style={{ gap: 4, marginTop: 4 }}>
                              {v.flags.filter((f) => FLAG_CHIP[f]).map((f) => <span key={f} className="tag tag-line">{FLAG_CHIP[f]}</span>)}
                            </div>
                          )}
                          {v.rank <= 15 && (v.llm_rank ?? 0) > 30 && (
                            <div className="row" style={{ gap: 4, marginTop: 4 }}>
                              <span className="tag">Only TasteRoute ranks this high</span>
                            </div>
                          )}
                        </td>
                        <td data-label="Fit" className="num">
                          <span className="score">{pct(v.fit)}</span>
                          <div className="fitbar" aria-hidden="true"><span style={{ width: `${pct(v.fit)}%` }} /></div>
                        </td>
                        <td data-label="Lift">
                          <Tip label={<span className={v.lift > 0.005 ? "lift-up" : "lift-flat"}>{liftText(v.lift, v.popularity_pct != null)}</span>}>
                            {v.popularity_pct != null
                              ? `Taste percentile ${pct(v.target_pct)} vs mass-market taste percentile ${pct(v.baseline_pct)}. Popularity (Qloo) ${pct(v.popularity_pct)}.`
                              : `Taste percentile ${pct(v.target_pct)} vs popularity percentile ${pct(v.baseline_pct)}.`}
                          </Tip>
                        </td>
                        <td data-label="Confidence"><ConfidenceBadge level={v.confidence} /></td>
                        <td data-label="Best product">
                          {v.best_product ? (
                            <>
                              <div style={{ fontWeight: 500 }}>{v.best_product.name}</div>
                              <div className="mono faint">
                                {FIT_TIP[v.best_product.label ?? ""] ? <Tip label={FIT_LABEL[v.best_product.label ?? ""] ?? ""}>{FIT_TIP[v.best_product.label ?? ""] ?? ""}</Tip> : FIT_LABEL[v.best_product.label ?? ""] ?? ""}
                              </div>
                            </>
                          ) : <span className="faint">–</span>}
                        </td>
                        <td data-label="Why" className="cell-wide" data-tour={i === 0 ? "reason" : undefined}>
                          <details className="reason small">
                            <summary><span className="clamp">{v.reason}</span></summary>
                            <p style={{ marginTop: 8 }}><ReasonText text={v.reason ?? ""} traceHref={`/runs/${id}/trace`} /></p>
                            <Link className="link small" href={`/runs/${id}/venues/${v.venue_id}`}>{v.evidence_count} evidence items →</Link>
                          </details>
                        </td>
                        <td data-label="Contact" className="small muted">{CONTACT_STATUS[v.contact_status] ?? v.contact_status}</td>
                        {llm && <td data-label="LLM rank" className="num">{v.llm_rank ?? "–"}</td>}
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
                  <button className="link" style={{ color: "#979797" }} onClick={cancel}>Cancel</button>
                  <button className="btn" disabled={run.status === "outreach_running"} onClick={findContacts}>Find contacts &amp; draft →</button>
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
      <Tour steps={TOUR} ready={!!page} next={items[0] ? { href: `/runs/${id}/venues/${(items.find((v) => v.rank === 1) ?? items[0]).venue_id}?tour=1`, label: "Open venue #1" } : undefined} />
    </RunShell>
  );
}
