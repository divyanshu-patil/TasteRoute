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
import { CONFIDENCE, CONTACT_STATUS, FIT_LABEL, FIT_TIP, FLAG_CHIP, LIFT_TIP_MASS, km, kmText, liftText, pct, venueTypeLabel } from "../../../../../lib/format";

const TOUR: TourStep[] = [
  { target: "venue-scores", title: "One venue, all its numbers", body: "Fit and lift, and the Qloo percentiles behind them: taste for your brands' fans, the same venues' taste for mass-market brands, and plain popularity." },
  { target: "why", title: "The reason", body: "Built from Qloo's explanation: which of your brands' fans drive the match and who goes here. Labels show what came from Qloo." },
  { target: "product-fit", title: "Which product to lead with", body: "A separate Qloo query per product. The lead product is the one this venue stands out most for among its type; \"close call\" means the gap is small." },
  { target: "shared-tastes", title: "Shared tastes beyond food and drink", body: "Qloo's cross-domain data: the artists your brands' fans like, and how this venue's guests score with those artists' fans. It explains the match and can open a pitch; it never changes fit." },
  { target: "evidence", title: "Every source", body: "Each item says whether it came from Qloo, the public web or our inference, and the map shows where the venue is." },
];

type Fit = { product_id: string; name: string; percentile: number; affinity: number | null; is_best: boolean; label: string | null; margin: number | null };

function EvidenceBody({ e }: { e: S["EvidenceOut"] }) {
  const v = e.value as Record<string, unknown>;
  const list = (k: string) => (Array.isArray(v[k]) ? (v[k] as unknown[]) : []);
  switch (e.type) {
    case "qloo_affinity":
      return v.baseline === "mass_market"
        ? <p className="small muted">Taste percentile {pct(Number(v.target_pct))} · mass-market taste percentile {pct(Number(v.baseline_pct))} · popularity percentile {pct(Number(v.popularity_pct))} · Qloo affinity {Number(v.affinity ?? 0).toFixed(3)} · popularity {Number(v.popularity ?? 0).toFixed(3)}</p>
        : <p className="small muted">Taste percentile {pct(Number(v.target_pct))} · popularity percentile {pct(Number(v.baseline_pct))} · Qloo affinity {Number(v.affinity ?? 0).toFixed(3)} · popularity {Number(v.popularity ?? 0).toFixed(3)}</p>;
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

  if (error) return (
    <div className="wrap">
      {error.status === 404 && error.detail.startsWith("Run") ? <NotFoundPanel /> : (
        <ErrorPanel code={error.code} title={error.status === 404 ? "Venue not found" : error.status === 0 ? "Can't reach the TasteRoute API" : error.title}>
          <p>{error.status === 404 ? "This venue isn't in this run's list." : error.detail || "Try again in a moment."}</p>
          <div className="row"><Link className="btn" href={`/runs/${id}`}>← Back to results</Link></div>
        </ErrorPanel>
      )}
    </div>
  );
  if (!d) return <div className="wrap"><Skeleton rows={8} /></div>;
  const v = d.venue;
  const here = d.lat != null && d.lon != null ? { lat: d.lat, lon: d.lon } : null;
  const pin: Pin[] = here ? [{ id: v.venue_id, ...here, label: String(v.rank), title: v.name, sub: d.address ?? undefined }] : [];
  if (here && d.base) pin.push({ id: "base", lat: d.base.lat, lon: d.base.lon, label: "You", title: d.base.label, sub: d.base.detail, base: true });
  const fits = d.product_fit as Fit[];
  const music = d.evidence.find((e) => e.type === "qloo_cross_domain")?.value as { artists: string[]; fans_like: string[]; pct: number } | undefined;
  const qloo = d.evidence.filter((e) => e.source_kind === "qloo" && e.type !== "qloo_cross_domain");
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
          {v.flags.filter((f) => FLAG_CHIP[f]).map((f) => <span key={f} className="tag tag-line">{FLAG_CHIP[f]}</span>)}
        </div>
        <h1 className="display d-l">{v.name}</h1>
        {v.flags.includes("signal_brand_venue") && <p className="muted">This is one of the brands you resemble, so it is hidden from the list by default.</p>}
        {v.flags.includes("maker_competitor") && <p className="muted">Qloo tags this venue as a maker of what you sell, so it may be a competitor rather than a stockist.</p>}
        <p className="muted">
          {d.address}
          {here && d.base && <> · {kmText(km(d.base, here))} from your business</>}
          {d.website && <> · <a className="link-mint" href={d.website} target="_blank" rel="noreferrer">website ↗</a></>}
        </p>
      </header>

      <section className="grid-4" data-tour="venue-scores">
        <div className="stat"><span className="label"><Tip label="Fit">0.7 × taste percentile + 0.3 × positive lift, as 0–100.</Tip></span><span className="v">{pct(v.fit)}</span><span className="mono faint">out of 100</span></div>
        <div className="stat"><span className="label"><Tip label="Lift">{v.popularity_pct != null ? `${LIFT_TIP_MASS}: taste percentile minus mass-market taste percentile.` : "Taste percentile minus popularity percentile. Positive means the match is about taste, not footfall."}</Tip></span><span className="v">{pct(v.lift) > 0 ? "+" : ""}{pct(v.lift)}</span><span className="mono faint">{liftText(v.lift, v.popularity_pct != null)}</span></div>
        <div className="stat"><span className="label">Taste percentile</span><span className="v">{pct(v.target_pct)}</span><span className="mono faint">among {venueTypeLabel(v.venue_type).toLowerCase()} venues, from Qloo affinity</span></div>
        {v.popularity_pct != null ? (
          <div className="stat"><span className="label">Popularity (Qloo)</span><span className="v">{pct(v.popularity_pct)}</span><span className="mono faint">percentile · mass-market taste {pct(v.baseline_pct)}{v.flags.includes("generic_missing") ? " (no reading)" : ""}</span></div>
        ) : (
          <div className="stat"><span className="label">Popularity percentile</span><span className="v">{pct(v.baseline_pct)}</span><span className="mono faint">Qloo popularity baseline{v.flags.includes("not_in_baseline") ? " · not in the top 50" : ""}</span></div>
        )}
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
            <span className="tag">Qloo, per product</span>
          </div>
          {fits.length === 0 && <p className="muted">Not scored.</p>}
          {fits.map((f) => (
            <div key={f.product_id} className="pfit">
              <span style={{ fontWeight: f.is_best ? 600 : 450 }}>{f.name}{f.is_best && <span className="mono faint"> · {FIT_TIP[f.label ?? ""] ? <Tip label={FIT_LABEL[f.label ?? ""]}>{FIT_TIP[f.label ?? ""] ?? ""}</Tip> : FIT_LABEL[f.label ?? ""]}</span>}</span>
              <span className="track" role="img" aria-label={`${f.name}: ${pct(f.percentile)} out of 100`}><span className={`fill ${f.is_best ? "" : "alt"}`} style={{ width: `${pct(f.percentile)}%`, display: "block" }} /></span>
              <Tip label={<span className="mono">{pct(f.percentile)}</span>}>{f.affinity != null ? `Qloo affinity ${f.affinity.toFixed(3)} for ${f.name}` : `Percentile ${pct(f.percentile)}`}</Tip>
            </div>
          ))}
          <p className="small faint">Each score (0–100) is this venue&apos;s percentile for one product among its type, from a separate Qloo query using only that product&apos;s brands. The lead product is the one this venue stands out most for{fits.some((f) => f.affinity != null) ? ", by standardised Qloo affinity" : ""}.</p>
        </div>
      </section>

      {music && (
        <section className="card stack-s" aria-labelledby="music-h" data-tour="shared-tastes">
          <div className="row between">
            <h2 id="music-h" className="h2">Shared tastes beyond food and drink</h2>
            <SourceChip kind="qloo" />
          </div>
          <p>Fans of the brands you resemble over-index on these artists:</p>
          <div className="chips">
            {music.fans_like.map((a) => <span key={a} className={music.artists.includes(a) ? "tag" : "tag tag-line"}>{a}</span>)}
          </div>
          <p>
            With those artists&apos; fans, this venue&apos;s percentile is {pct(music.pct)} among the {venueTypeLabel(v.venue_type).toLowerCase()} venues
            ranked here (100 is the highest){music.artists.length > 0 ? `, mostly through fans of ${music.artists.join(" and ")}` : ""}.
          </p>
          <p className="small faint">
            Context for a pitch, not part of fit: in our backtest, ranking by music taste did not find more real accounts.{" "}
            <Link className="link" href="/evaluation">See the backtest</Link>
          </p>
        </section>
      )}

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
