"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { EmptyState, ErrorPanel, Skeleton } from "../../components/ui";
import { useAccount } from "../../lib/account";
import { ApiError, api } from "../../lib/api";
import { ago } from "../../lib/format";

type RunItem = { id: string; status: string; city: string; brand: string; created_at: string };

export default function Runs() {
  const { enabled, user } = useAccount();
  const email = user?.email;
  const [runs, setRuns] = useState<RunItem[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let alive = true;
    setError(null);
    api<RunItem[]>("/v1/runs")
      .then((r) => alive && setRuns(r))
      .catch((e: unknown) => alive && setError(e instanceof ApiError ? e : new ApiError(0, "network_error", "Can't reach the TasteRoute API", "")));
    return () => {
      alive = false;
    };
  }, [attempt]);
  return (
    <div className="wrap stack" style={{ gap: 32 }}>
      <h1 className="display d-l">All runs</h1>
      <p className="muted">
        {email ? `Every run from any device you logged in on, saved to your account (${email}).`
          : enabled ? "Runs live in this browser. Log in to save them and see them on any device."
          : "Runs live in this browser's anonymous workspace. Clearing site data starts a new one."}
      </p>
      {error && !runs ? (
        <ErrorPanel code={error.code} title={error.status === 0 ? "Can't reach the TasteRoute API" : error.title}>
          <p className="muted">{error.detail || "Your runs are safe; try again in a moment."}</p>
          <div className="row">
            <button className="btn" onClick={() => setAttempt(attempt + 1)}>Retry</button>
            <Link className="btn-ghost" href="/sample">See the sample run</Link>
          </div>
        </ErrorPanel>
      ) : !runs ? <Skeleton rows={4} /> : runs.length === 0 ? (
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
