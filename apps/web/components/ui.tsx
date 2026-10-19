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

export const NOTHING_SENT = "Nothing is sent from Stockist Scout. You send approved emails from your own inbox.";
