"use client";

import Link from "next/link";
import { useState } from "react";
import type { S } from "../lib/api";
import { pct, venueTypeLabel } from "../lib/format";

type Row = S["VenueRow"];
type Item = { label: string; n: number; mean: number; href?: string };
type Tip = { x: number; y: number; text: string[] } | null;
const CONF = [
  { key: "high", label: "High confidence", fill: "#000000" },
  { key: "medium", label: "Medium", fill: "#6b6b6b" },
  { key: "low", label: "Low", fill: "#c6c6c6" },
];
const BANDS = [
  { label: "Low", sub: "0–39", lo: 0, hi: 40 },
  { label: "Fair", sub: "40–59", lo: 40, hi: 60 },
  { label: "Good", sub: "60–79", lo: 60, hi: 80 },
  { label: "Great", sub: "80–100", lo: 80, hi: 101 },
];
const GOOD_FIT = 60; // the "Good" band starts here; also the gems chart's vertical split

/** The run at a glance, in plain words, from the venues shown (filters apply). Every number is the stored Qloo result. */
export function RunCharts({ rows, runId, mass }: { rows: Row[]; runId: string; mass: boolean }) {
  if (rows.length < 2) return null;
  const top = rows.slice(0, 10);
  const conf = CONF.map((c) => ({ ...c, n: rows.filter((v) => v.confidence === c.key).length }));
  const bands = BANDS.map((b) => ({ ...b, n: rows.filter((v) => pct(v.fit) >= b.lo && pct(v.fit) < b.hi).length }));
  const gems = rows.filter((v) => pct(v.fit) >= GOOD_FIT && pct(v.lift) > 0);
  const products = group(rows, (v) => v.best_product?.name ?? "").filter((p) => p.label);
  const types = group(rows, (v) => venueTypeLabel(v.venue_type)).sort((a, b) => b.mean - a.mean);
  const llm = rows.some((v) => v.llm_rank != null);
  const missed = rows.filter((v) => v.rank <= 15 && (v.llm_rank ?? 0) > 30);
  const best = top[0]!;
  const strong = bands[2]!.n + bands[3]!.n;
  const big = mass ? "big-name brands" : "plain popularity";
  return (
    <section className="stack-s" aria-labelledby="charts-h">
      <div className="stack-s">
        <h2 id="charts-h" className="label">Your results at a glance</h2>
        <p className="small muted">
          <strong>Fit</strong> is a score from 0 to 100: how closely a venue&apos;s guests share your customers&apos; taste, from Qloo. Higher is better.{" "}
          <strong>Lift</strong> says whether that taste is special to brands like yours, or whether {big} do just as well there.
        </p>
      </div>
      <div className="grid-2">
        <Card title="Your 10 best matches" hint="Longer bar = closer taste match. Click a name to see why." lead={<><Link className="link" href={`/runs/${runId}/venues/${best.venue_id}`}>{best.name}</Link> is your strongest match, with a fit of {pct(best.fit)}.</>}>
          <Bars items={top.map((v) => ({ label: `${v.rank}. ${v.name}`, n: pct(v.fit), mean: v.fit, href: `/runs/${runId}/venues/${v.venue_id}` }))} max={100} value={(i) => `${i.n}`} />
        </Card>

        <Card title="Hidden gems" lead={gems.length > 0
          ? <>{gems.length} {gems.length === 1 ? "venue is a" : "venues are"} hidden {gems.length === 1 ? "gem" : "gems"}: a good fit, and their guests prefer brands like yours over {big}.</>
          : <>No hidden gems yet: your good matches suit {big} just as well.</>}>
          <Gems rows={rows} runId={runId} />
        </Card>

        <Card title="How good the matches are" hint="Black columns are the venues worth pitching first." lead={<>{strong} of {rows.length} venues are a good or great fit.</>}>
          <Columns bands={bands} />
        </Card>

        <Card title="How sure we are" hint="High confidence = a strong fit backed by more than one of your reference brands." lead={conf[0]!.n > 0 ? <>{conf[0]!.n} of {rows.length} venues are a high-confidence match. Start with those.</> : <>No venue is a high-confidence match yet. Start with the medium ones.</>}>
          <Donut parts={conf} total={rows.length} />
        </Card>

        {products.length > 0 && (
          <Card title="Which product to pitch" hint="Each venue counts once, for the product that fits it best." lead={<>Lead with <strong>{products[0]!.label}</strong>: it&apos;s the best fit at {products[0]!.n} of {rows.length} venues.</>}>
            <Bars items={products} max={rows.length} value={(i) => `${i.n} ${i.n === 1 ? "venue" : "venues"}`} />
          </Card>
        )}

        {types.length > 1 && (
          <Card title="Which kinds of venue suit you" hint="Average fit of every venue of that kind." lead={<>{types[0]!.label} venues suit you best, with an average fit of {pct(types[0]!.mean)}.</>}>
            <Bars items={types.map((t) => ({ ...t, n: pct(t.mean) }))} max={100} value={(i) => `fit ${i.n}`} />
          </Card>
        )}

        {llm && (
          <Card title="What only TasteRoute found" hint="These are the venues Qloo's taste data surfaced that a name-only guess would skip." lead={missed.length > 0
            ? <>{missed.length} of your top 15 would be easy to miss: an AI guessing from names alone ranked them below 30.</>
            : <>An AI guessing from names alone agreed with most of your top 15.</>}>
            {missed.length > 0 && (
              <ul className="chart-list small">
                {missed.map((v) => <li key={v.venue_id}><Link className="link" href={`/runs/${runId}/venues/${v.venue_id}`}>{v.rank}. {v.name}</Link><span className="mono faint">AI put it at {v.llm_rank}</span></li>)}
              </ul>
            )}
          </Card>
        )}
      </div>
    </section>
  );
}

function Card({ title, lead, hint, children }: { title: string; lead: React.ReactNode; hint?: string; children: React.ReactNode }) {
  return (
    <figure className="card stack-s" style={{ margin: 0 }}>
      <figcaption className="stack-s">
        <span className="label">{title}</span>
        <span className="chart-lead">{lead}</span>
      </figcaption>
      {children}
      {hint && <p className="mono faint chart-hint">{hint}</p>}
    </figure>
  );
}

function group(rows: Row[], key: (v: Row) => string): Item[] {
  const m = new Map<string, number[]>();
  for (const v of rows) m.set(key(v), [...(m.get(key(v)) ?? []), v.fit]);
  return [...m].map(([label, fits]) => ({ label, n: fits.length, mean: fits.reduce((a, b) => a + b, 0) / fits.length }))
    .sort((a, b) => b.n - a.n || b.mean - a.mean);
}

function Bars({ items, max, value }: { items: Item[]; max: number; value: (i: Item) => string }) {
  return (
    <ul className="chart-bars">
      {items.slice(0, 8).map((i, k) => (
        <li key={i.label} title={`${i.label}: ${value(i)}`}>
          <span className="small chart-bar-label">{i.href ? <Link href={i.href}>{i.label}</Link> : i.label}</span>
          <span className="chart-bar-track"><span style={{ width: `${(i.n / max) * 100}%`, background: k === 0 ? "#000" : "#6b6b6b" }} /></span>
          <span className="mono">{value(i)}</span>
        </li>
      ))}
    </ul>
  );
}

function Bubble({ at, w, h }: { at: Tip; w: number; h: number }) {
  if (!at) return null;
  return (
    <div className="chart-tip mono" style={{ left: `${(at.x / w) * 100}%`, top: `${(at.y / h) * 100}%` }}>
      {at.text.map((t) => <div key={t}>{t}</div>)}
    </div>
  );
}

/** Fit across, lift up, split into four plainly named corners. */
function Gems({ rows, runId }: { rows: Row[]; runId: string }) {
  const [tip, setTip] = useState<Tip>(null);
  const W = 520, H = 320, L = 12, R = 12, T = 12, B = 28;
  const lifts = rows.map((v) => pct(v.lift));
  const lo = Math.min(-5, ...lifts) - 3;
  const hi = Math.max(5, ...lifts) + 3;
  const x = (n: number) => L + (n / 100) * (W - L - R);
  const y = (n: number) => T + ((hi - n) / (hi - lo)) * (H - T - B);
  const corner = (text: string, ax: number, ay: number, anchor: "start" | "end") => (
    <text x={ax} y={ay} textAnchor={anchor} className="chart-corner">{text}</text>
  );
  return (
    <div className="chart-box">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Each venue by fit and lift, split into hidden gems, popular picks, niche and lower priority" onMouseLeave={() => setTip(null)}>
        <rect x={x(GOOD_FIT)} y={T} width={x(100) - x(GOOD_FIT)} height={y(0) - T} className="chart-gem-zone" />
        <line x1={L} x2={W - R} y1={y(0)} y2={y(0)} className="chart-split" />
        <line x1={x(GOOD_FIT)} x2={x(GOOD_FIT)} y1={T} y2={H - B} className="chart-split" />
        {corner("HIDDEN GEMS", W - R - 6, T + 16, "end")}
        {corner("POPULAR PICKS", W - R - 6, H - B - 8, "end")}
        {corner("NICHE", L + 6, T + 16, "start")}
        {corner("LOWER PRIORITY", L + 6, H - B - 8, "start")}
        <text x={L} y={H - 8} className="chart-axis-text">Weaker fit</text>
        <text x={W - R} y={H - 8} textAnchor="end" className="chart-axis-text">Stronger fit →</text>
        {[...rows].reverse().map((v) => {
          const cx = x(pct(v.fit));
          const cy = y(pct(v.lift));
          const gem = pct(v.fit) >= GOOD_FIT && pct(v.lift) > 0;
          const show = () => setTip({ x: cx, y: cy, text: [`${v.rank}. ${v.name}`, `fit ${pct(v.fit)} · lift ${pct(v.lift) > 0 ? "+" : ""}${pct(v.lift)}`] });
          return (
            <Link key={v.venue_id} href={`/runs/${runId}/venues/${v.venue_id}`} aria-label={`${v.rank}. ${v.name}, fit ${pct(v.fit)}, lift ${pct(v.lift)}`} onMouseEnter={show} onFocus={show}>
              <circle cx={cx} cy={cy} r={12} fill="transparent" />
              <circle cx={cx} cy={cy} r={gem ? 6 : 4.5} fill={gem ? "#000" : "#a8a8a8"} stroke="#fff" strokeWidth={2} />
            </Link>
          );
        })}
      </svg>
      <Bubble at={tip} w={W} h={H} />
      <p className="mono faint chart-hint">Right = stronger fit. Up = guests prefer brands like yours over big names. The green corner holds the gems; hover or tap a dot.</p>
    </div>
  );
}

function Columns({ bands }: { bands: { label: string; sub: string; n: number }[] }) {
  const max = Math.max(1, ...bands.map((b) => b.n));
  return (
    <div className="chart-cols" role="img" aria-label={bands.map((b) => `${b.label} fit (${b.sub}): ${b.n}`).join(", ")}>
      {bands.map((b, i) => (
        <div key={b.label} className="chart-col" title={`${b.n} ${b.n === 1 ? "venue" : "venues"} with a ${b.label.toLowerCase()} fit (${b.sub})`}>
          <span className="mono">{b.n}</span>
          <span className="chart-col-bar" style={{ height: `${(b.n / max) * 100}%`, background: i >= 2 ? "#000" : "#a8a8a8" }} />
          <span className="small"><strong>{b.label}</strong></span>
          <span className="mono faint">{b.sub}</span>
        </div>
      ))}
    </div>
  );
}

function Donut({ parts, total }: { parts: { key: string; label: string; fill: string; n: number }[]; total: number }) {
  const r = 52, c = 2 * Math.PI * r;
  let at = 0;
  return (
    <div className="row" style={{ gap: 24, alignItems: "center" }}>
      <svg viewBox="0 0 140 140" width="140" height="140" role="img" aria-label={parts.map((p) => `${p.label}: ${p.n}`).join(", ")}>
        <circle cx="70" cy="70" r={r} fill="none" stroke="var(--mist)" strokeWidth="18" />
        {parts.filter((p) => p.n > 0).map((p) => {
          const len = (p.n / total) * c;
          const seg = <circle key={p.key} aria-hidden="true" cx="70" cy="70" r={r} fill="none" stroke={p.fill} strokeWidth="18"
            strokeDasharray={`${Math.max(0, len - 2)} ${c}`} strokeDashoffset={-at} transform="rotate(-90 70 70)" />;
          at += len;
          return seg;
        })}
        <text x="70" y="72" textAnchor="middle" className="chart-donut-v">{parts[0]!.n}</text>
        <text x="70" y="92" textAnchor="middle" className="chart-axis-text">high</text>
      </svg>
      <ul className="chart-legend" style={{ flex: 1, minWidth: 140 }}>
        {parts.map((p) => (
          <li key={p.key} className="small"><i style={{ background: p.fill }} aria-hidden="true" />{p.label}<strong>{p.n}</strong></li>
        ))}
      </ul>
    </div>
  );
}
