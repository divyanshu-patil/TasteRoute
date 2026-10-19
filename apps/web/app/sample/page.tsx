"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { EmptyState, ErrorPanel, Skeleton } from "../../components/ui";
import { API_URL } from "../../lib/api";

export default function Sample() {
  const router = useRouter();
  const [state, setState] = useState<"loading" | "missing" | "unreachable">("loading");
  const load = useCallback(() => {
    setState("loading");
    fetch(`${API_URL}/v1/demo`)
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json() as Promise<{ run_id: string | null; available: boolean }>;
      })
      .then((d) => (d.available && d.run_id ? router.replace(`/runs/${d.run_id}${window.location.search}`) : setState("missing")))
      .catch(() => setState("unreachable"));
  }, [router]);
  useEffect(load, [load]);
  return (
    <div className="wrap stack">
      <h1 className="display d-l">Sample run</h1>
      {state === "loading" && <Skeleton rows={6} />}
      {state === "missing" && (
        <EmptyState title="The sample run isn't available right now">
          <Link className="btn" href="/start">Start your own run</Link>
        </EmptyState>
      )}
      {state === "unreachable" && (
        <ErrorPanel code="network_error" title="Can't reach the TasteRoute API">
          <p>The sample run is stored on our API, which didn't answer. It may be waking up; try again in a moment.</p>
          <div>
            <button className="btn" onClick={load}>Try again</button>
          </div>
        </ErrorPanel>
      )}
    </div>
  );
}
