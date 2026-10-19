"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ReasonText } from "../../../../../components/reason";
import { NotFoundPanel } from "../../../../../components/run-shell";
import { Tour, type TourStep } from "../../../../../components/tour";
import { ConfidenceBadge, ContactSource, ErrorPanel, Skeleton, SourceChip, Tip } from "../../../../../components/ui";
import { VenueMap, type Pin } from "../../../../../components/venue-map";
import { ApiError, api, type S } from "../../../../../lib/api";
import { CONFIDENCE, CONTACT_STATUS, FIT_LABEL, km, kmText, liftText, pct, venueTypeLabel } from "../../../../../lib/format";

const TOUR: TourStep[] = [
  { target: "venue-scores", title: "One venue, all its numbers", body: "Fit and lift, and the two Qloo percentiles behind them: taste for your brands' fans, and plain popularity." },
  { target: "why", title: "The reason", body: "Built from Qloo's explanation: which of your brands' fans drive the match and who goes here. Labels show what came from Qloo." },
  { target: "product-fit", title: "Which product to lead with", body: "A separate Qloo query per product. The longest bar is the one to pitch first; \"close call\" means the gap is small." },
  { target: "evidence", title: "Every source", body: "Each item says whether it came from Qloo, the public web or our inference, and the map shows where the venue is." },
];

type Fit = { product_id: string; name: string; percentile: number; is_best: boolean; label: string | null; margin: number | null };

function EvidenceBody({ e }: { e: S["EvidenceOut"] }) {
  const v = e.value as Record<string, unknown>;
  const list = (k: string) => (Array.isArray(v[k]) ? (v[k] as unknown[]) : []);
  switch (e.type) {
    case "qloo_affinity":
      return <p className="small muted">Taste percentile {pct(Number(v.target_pct))} · popularity percentile {pct(Number(v.baseline_pct))} · Qloo affinity {Number(v.affinity ?? 0).toFixed(3)} · popularity {Number(v.popularity ?? 0).toFixed(3)}</p>;
    case "qloo_explanation":
      return (
        <div className="chips">
          {list("drivers").map((d) => {
            const x = d as { name: string; score: number };
            return <span key={x.name} className="tag tag-line">{x.name} · {Math.round(x.score * 100)}%</span>;
          })}
        </div>
      );
    case "qloo_tag_overlap":
      return <div className="chips">{list("tags").map((t) => <span key={String(t)} className="tag">{String(t)}</span>)}</div>;
    case "qloo_venue_profile":
      return (
        <div className="stack-s">
          <div className="chips">{list("crowd").map((t) => <span key={String(t)} className="tag tag-line">{String(t)}</span>)}</div>
          <div className="chips">{list("interests").map((t) => <span key={String(t)} className="tag">{String(t)}</span>)}</div>
          {typeof v.description === "string" && v.description && <p className="small muted">{v.description}</p>}
        </div>
      );
    case "osm_fact":
      return <p className="small muted">{Object.entries(v).filter(([k]) => k !== "osm_id").map(([k, x]) => `${k}: ${String(x)}`).join(" · ")}</p>;
    case "contact_source":
      return <p className="small muted">{String(v.source)} · {(list("sources")[0] as { uri?: string } | undefined)?.uri ?? ""}</p>;
    default:
      return null;
  }
}

export default function VenuePage() {
  const { id, venueId } = useParams<{ id: string; venueId: string }>();
  const [d, setD] = useState<S["VenueDetail"] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    let alive = true;
    api<S["VenueDetail"]>(`/v1/runs/${id}/venues/${venueId}`)
      .then((x) => alive && setD(x))
      .catch((e: unknown) => alive && setError(e instanceof ApiError ? e : new ApiError(0, "error", "Failed", "")));
    return () => {
      alive = false;
    };
  }, [id, venueId]);

  if (error) return <div className="wrap">{error.status === 404 ? <NotFoundPanel /> : <ErrorPanel code={error.code} title={error.title} />}</div>;
  if (!d) return <div className="wrap"><Skeleton rows={8} /></div>;
  const v = d.venue;
  const here = d.lat != null && d.lon != null ? { lat: d.lat, lon: d.lon } : null;
  const pin: Pin[] = here ? [{ id: v.venue_id, ...here, label: String(v.rank), title: v.name, sub: d.address ?? undefined }] : [];
  if (here && d.base) pin.push({ id: "base", lat: d.base.lat, lon: d.base.lon, label: "You", title: d.base.label, sub: d.base.detail, base: true });
  const fits = d.product_fit as Fit[];
  const qloo = d.evidence.filter((e) => e.source_kind === "qloo");
  const other = d.evidence.filter((e) => e.source_kind !== "qloo");

  return (
    <div className="wrap stack" style={{ gap: 32 }}>
      <Link className="link" href={`/runs/${id}`}>← Back to results</Link>
      <header className="stack">
        <div className="row">
          <span className="tag tag-ink">#{v.rank}</span>
          <span className="tag tag-mist">{venueTypeLabel(v.venue_type)}</span>
          {v.neighborhood && <span className="tag tag-mist">{v.neighborhood}</span>}
          <ConfidenceBadge level={v.confidence} />
        </div>
        <h1 className="display d-l">{v.name}</h1>
        <p className="muted">
          {d.address}
          {here && d.base && <> · {kmText(km(d.base, here))} from your business</>}
          {d.website && <> · <a className="link-mint" href={d.website} target="_blank" rel="noreferrer">website ↗</a></>}
        </p>
      </header>

      <section className="grid-4" data-tour="venue-scores">
        <div className="stat"><span className="label"><Tip label="Fit">0.7 × taste percentile + 0.3 × positive lift, as 0–100.</Tip></span><span className="v">{pct(v.fit)}</span><span className="mono faint">out of 100</span></div>
        <div className="stat"><span className="label"><Tip label="Lift">Taste percentile minus popularity percentile. Positive means the match is about taste, not footfall.</Tip></span><span className="v">{pct(v.lift) > 0 ? "+" : ""}{pct(v.lift)}</span><span className="mono faint">{liftText(v.lift)}</span></div>
        <div className="stat"><span className="label">Taste percentile</span><span className="v">{pct(v.target_pct)}</span><span className="mono faint">among {venueTypeLabel(v.venue_type).toLowerCase()} venues, from Qloo affinity</span></div>
        <div className="stat"><span className="label">Popularity percentile</span><span className="v">{pct(v.baseline_pct)}</span><span className="mono faint">Qloo popularity baseline{v.flags.includes("not_in_baseline") ? " · not in the top 50" : ""}</span></div>
      </section>

      <section className="grid-2">
        <div className="card stack" data-tour="why">
          <h2 className="h2">Why this venue</h2>
          <p style={{ fontSize: 18, lineHeight: 1.4 }}><ReasonText text={v.reason ?? ""} traceHref={`/runs/${id}/trace`} /></p>
          <p className="small faint">Confidence: {CONFIDENCE[v.confidence]}</p>
        </div>
        <div className="card stack" data-tour="product-fit">
          <div className="row between">
            <h2 className="h2">Product fit</h2>
            <SourceChip kind="inference" />
          </div>
          {fits.length === 0 && <p className="muted">Not scored.</p>}
          {fits.map((f) => (
            <div key={f.product_id} className="bar">
              <span style={{ fontWeight: f.is_best ? 600 : 450 }}>{f.name}{f.is_best && <span className="mono faint"> · {FIT_LABEL[f.label ?? ""]}</span>}</span>
              <span className="track" role="img" aria-label={`${f.name}: ${pct(f.percentile)} percentile`}><span className={`fill ${f.is_best ? "" : "alt"}`} style={{ width: `${pct(f.percentile)}%`, display: "block" }} /></span>
              <span className="mono">{pct(f.percentile)}</span>
            </div>
          ))}
          <p className="small faint">Each bar is this venue&apos;s percentile for one product, from a separate Qloo query using only that product&apos;s brands.</p>
        </div>
      </section>

      <section className="stack" data-tour="evidence">
        <div className="row between">
          <h2 className="display d-m">Evidence</h2>
          <Link className="link-mint" href={`/runs/${id}/trace`}>See every call in the trace →</Link>
        </div>
        <div className="grid-2">
          <div className="evidence">
            {qloo.map((e) => (
              <article key={e.id} className="ev">
                <div className="row between"><strong>{e.label}</strong><SourceChip kind="qloo" /></div>
                <EvidenceBody e={e} />
                {e.stale && <span className="mono faint">older than 30 days</span>}
              </article>
            ))}
          </div>
          <div className="evidence">
            {d.lat != null && d.lon != null && (
              <article className="ev" style={{ padding: 0, overflow: "hidden" }}>
                <VenueMap pins={pin} label={`Map: ${v.name}`} height={240} />
              </article>
            )}
            {other.map((e) => (
              <article key={e.id} className="ev">
                <div className="row between"><strong>{e.label}</strong><SourceChip kind={e.source_kind} /></div>
                <EvidenceBody e={e} />
              </article>
            ))}
            <article className="ev" style={{ background: "#fff" }}>
              <div className="row between"><strong>Contact</strong><span className="mono faint">{CONTACT_STATUS[v.contact_status]}</span></div>
              {d.contacts.map((c) => (
                <p key={c.id} className="small"><span className="email">{c.email}</span> <span className="mono faint"><ContactSource contact={c} />{c.role ? ` · ${c.role}` : ""}</span></p>
              ))}
              {d.checked_sources.length > 0 && <p className="mono faint">checked: {d.checked_sources.join(", ")}</p>}
            </article>
          </div>
        </div>
      </section>
      <Tour steps={TOUR} ready next={{ href: `/runs/${id}/outreach?tour=1`, label: "See the outreach" }} />
    </div>
  );
}
