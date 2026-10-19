import Link from "next/link";
import type { ReactNode } from "react";
import { CONFIDENCE } from "../lib/format";

export function Tip({ label, children }: { label: ReactNode; children: string }) {
  return (
    <span className="tip" tabIndex={0}>
      {label}
      <span className="tip-body" role="tooltip">
        {children}
      </span>
    </span>
  );
}

export function ConfidenceBadge({ level }: { level: string }) {
  return (
    <Tip label={<span className={`conf conf-${level}`}><i aria-hidden="true"><b /><b /><b /></i>{level}</span>}>
      {CONFIDENCE[level] ?? level}
    </Tip>
  );
}

export function SourceChip({ kind, href }: { kind: "qloo" | "inference" | "external" | string; href?: string }) {
  const [cls, text] = kind === "qloo" ? ["tag", "Qloo"] : kind === "inference" ? ["tag tag-mist", "Our inference"] : ["tag tag-line", "Public web"];
  if (href) return <Link className={cls} href={href} title="See the calls behind this in the trace">{text}</Link>;
  return <span className={cls}>{text}</span>;
}

export function Banner({ tone = "plain", children }: { tone?: "plain" | "warn" | "mint" | "ink"; children: ReactNode }) {
  return (
    <div className={`banner ${tone === "plain" ? "" : `banner-${tone}`}`} role={tone === "warn" ? "status" : undefined}>
      <span className="dot" aria-hidden="true" style={tone === "warn" ? { background: "#000" } : undefined} />
      <div className="stack-s small">{children}</div>
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty stack-s" style={{ alignItems: "center" }}>
      <p className="h3">{title}</p>
      {children}
    </div>
  );
}

export function ErrorPanel({ code, title, children }: { code?: string; title: string; children?: ReactNode }) {
  return (
    <section className="panel-error stack" role="alert">
      <p className="mono" style={{ color: "#979797" }}>ERROR{code ? <> · <code>{code}</code></> : null}</p>
      <h2 className="display d-m">{title}</h2>
      {children}
    </section>
  );
}

export function Skeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="table-wrap" aria-busy="true" aria-label="Loading">
      <div className="stack-s" style={{ padding: 16 }}>
        {Array.from({ length: rows }, (_, i) => (
          <div key={i} className="skeleton" style={{ width: `${92 - (i % 3) * 14}%` }} />
        ))}
      </div>
    </div>
  );
}

export const NOTHING_SENT = "Nothing is sent without your click. Emails go from your own Gmail when you're logged in, or you copy approved ones into your inbox.";

const CONTACT_SOURCE: Record<string, string> = { osm: "OpenStreetMap", website: "venue website", web: "web search", hunter: "Hunter", qloo: "Qloo" };

/** Where a contact was published, linked to that page, and whether the AI or a web search found it. */
export function ContactSource({ contact }: { contact: { source: string; sources: { [k: string]: unknown }[] } }) {
  const uri = contact.sources.find((x) => typeof x.uri === "string")?.uri as string | undefined;
  const label = `${CONTACT_SOURCE[contact.source] ?? contact.source}${contact.sources.some((x) => x.found_by === "ai") ? " · found by AI on the page" : ""}`;
  return uri && /^https?:\/\//i.test(uri)
    ? <a className="link" href={uri} target="_blank" rel="noopener noreferrer">{label} ↗</a>
    : <>{label}</>;
}
