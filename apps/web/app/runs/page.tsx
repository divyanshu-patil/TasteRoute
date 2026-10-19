"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { EmptyState, Skeleton } from "../../components/ui";
import { api } from "../../lib/api";
import { ago } from "../../lib/format";

type RunItem = { id: string; status: string; city: string; brand: string; created_at: string };

export default function Runs() {
  const [runs, setRuns] = useState<RunItem[] | null>(null);
  useEffect(() => {
    let alive = true;
    api<RunItem[]>("/v1/runs").then((r) => alive && setRuns(r)).catch(() => alive && setRuns([]));
    return () => {
      alive = false;
    };
  }, []);
  return (
    <div className="wrap stack" style={{ gap: 32 }}>
      <h1 className="display d-l">My runs</h1>
      <p className="muted">Runs live in this browser&apos;s anonymous workspace. Clearing site data starts a new one.</p>
      {!runs ? <Skeleton rows={4} /> : runs.length === 0 ? (
        <EmptyState title="No runs yet"><Link className="btn" href="/start">Start a run</Link></EmptyState>
      ) : (
        <ul className="stack-s" style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {runs.map((r) => (
            <li key={r.id}>
              <Link href={`/runs/${r.id}`} className="card row between" style={{ textDecoration: "none" }}>
                <span className="stack-s" style={{ gap: 4 }}>
                  <strong className="h3">{r.brand}</strong>
                  <span className="mono faint">{r.city} · {ago(r.created_at)}</span>
                </span>
                <span className={`status ${r.status === "done" || r.status === "scouted" ? "status-approved" : r.status === "failed" ? "status-edited" : ""}`}>{r.status}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
