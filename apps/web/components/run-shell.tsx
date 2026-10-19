"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import type { ApiError, S } from "../lib/api";
import { venueTypeLabel } from "../lib/format";
import { ErrorPanel, Skeleton } from "./ui";

const TABS = [
  { key: "results", label: "Results", href: "" },
  { key: "outreach", label: "Outreach", href: "/outreach" },
  { key: "trace", label: "Trace", href: "/trace" },
];

export function NotFoundPanel() {
  return (
    <ErrorPanel code="not_found" title="Run not found">
      <p>This run doesn&apos;t exist or belongs to another workspace.</p>
      <div className="row">
        <Link className="btn" href="/start">Start a run</Link>
        <Link className="btn-ghost" href="/sample">See the sample</Link>
      </div>
    </ErrorPanel>
  );
}

export function RunShell({ run, error, tab, online = true, children }: { run: S["RunOut"] | null; error: ApiError | null; tab: string; online?: boolean; children: ReactNode }) {
  if (error) return <div className="wrap">{error.status === 404 ? <NotFoundPanel /> : <ErrorPanel code={error.code} title={error.title}><p>{error.detail}</p></ErrorPanel>}</div>;
  if (!run) return <div className="wrap stack"><div className="skeleton" style={{ height: 80, width: "60%" }} /><Skeleton /></div>;
  const base = `/runs/${run.id}`;
  return (
    <div className="wrap stack" style={{ gap: 32 }}>
      <header className="stack" style={{ gap: 20 }}>
        <div className="row">
          {run.is_demo && <span className="tag tag-ink">Sample run · stored data · read-only</span>}
          <span className="tag tag-mist">{run.city.name as string}</span>
          {run.venue_types.map((t) => <span key={t} className="tag tag-mist">{venueTypeLabel(t)}</span>)}
          <span className="mono faint">RUN {run.id.slice(0, 8)}</span>
        </div>
        <h1 className="display d-l">{run.brand.name as string}</h1>
        <div className="row between">
          <nav className="tabs" aria-label="Run sections">
            {TABS.map((t) => (
              <Link key={t.key} href={base + t.href} aria-current={t.key === tab ? "page" : undefined}>{t.label}</Link>
            ))}
          </nav>
          <p className="mono muted">{run.products.map((p) => p.name as string).join(" · ")}</p>
        </div>
      </header>
      {!online && <div className="banner banner-warn" role="status"><span className="dot" style={{ background: "#000" }} />Connection lost. Reconnecting and catching up…</div>}
      {children}
    </div>
  );
}
