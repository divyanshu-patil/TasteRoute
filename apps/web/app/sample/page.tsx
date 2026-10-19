"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { EmptyState, Skeleton } from "../../components/ui";
import { API_URL } from "../../lib/api";

export default function Sample() {
  const router = useRouter();
  const [missing, setMissing] = useState(false);
  useEffect(() => {
    fetch(`${API_URL}/v1/demo`)
      .then((r) => r.json() as Promise<{ run_id: string | null; available: boolean }>)
      .then((d) => (d.available && d.run_id ? router.replace(`/runs/${d.run_id}`) : setMissing(true)))
      .catch(() => setMissing(true));
  }, [router]);
  return (
    <div className="wrap stack">
      <h1 className="display d-l">Sample run</h1>
      {missing ? (
        <EmptyState title="The sample run isn't available right now">
          <Link className="btn" href="/start">Start your own run</Link>
        </EmptyState>
      ) : (
        <Skeleton rows={6} />
      )}
    </div>
  );
}
