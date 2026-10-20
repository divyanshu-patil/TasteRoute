"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { RunShell } from "../../../../components/run-shell";
import { Tour, type TourStep } from "../../../../components/tour";
import { EmptyState, Skeleton } from "../../../../components/ui";
import { api, type S } from "../../../../lib/api";
import { useRun } from "../../../../lib/use-run";

const KINDS = [
  { key: "", label: "Everything" },
  { key: "tool", label: "Agent tools" },
  { key: "llm", label: "LLM" },
  { key: "qloo", label: "Qloo" },
  { key: "external", label: "Web & OSM" },
];

function brief(t: S["TraceRow"]): string {
  const d = t.detail as Record<string, unknown>;
  if (t.kind === "qloo") return `${String(d.status)} · ${d.cache_hit ? "cache hit" : `${String(d.duration_ms)} ms`} · ${String(d.result_count)} results`;
  if (t.kind === "llm") return `${String(d.status)} · ${String(d.duration_ms)} ms${d.tool_calls ? ` · called ${(d.tool_calls as string[]).join(", ")}` : ""}`;
  if (t.kind === "external") return `${String(d.status)} · ${d.cache_hit ? "cache hit" : `${String(d.duration_ms)} ms`}`;
  if (t.step === "decision") return `${String(d.by)} decided`;
  return t.step === "step_done" ? "done" : t.step === "tool_call" ? "called" : String(t.step);
}

function Saw({ saw }: { saw: Record<string, unknown> }) {
  const text = Object.entries(saw).filter(([k]) => k !== "rule").map(([k, v]) => `${k.replaceAll("_", " ")}: ${typeof v === "object" && v ? JSON.stringify(v).replace(/[{}"[\]]/g, "").replaceAll(",", ", ") : String(v)}`).join(" · ");
  return <p className="mono faint">Saw {text}{saw.rule ? ` · rule: ${String(saw.rule)}` : ""}</p>;
}

const TOUR: TourStep[] = [
  { target: "trace-filter", title: "Filter the trace", body: "Agent steps, LLM calls, Qloo calls and web lookups, each with a count." },
  { target: "trace", title: "Every call, in order", body: "Timings, cache hits and results for each call this run made. Decision rows show what the agent saw and why it acted. A rule checker approved every call; keys never appear." },
];

export default function Trace() {
  const { id } = useParams<{ id: string }>();
  const { run, error, online } = useRun(id);
  const [kind, setKind] = useState("");
  const [rows, setRows] = useState<S["TraceRow"][] | null>(null);

  useEffect(() => {
    let alive = true;
    api<S["TraceRow"][]>(`/v1/runs/${id}/trace${kind ? `?kind=${kind}` : ""}`).then((r) => alive && setRows(r)).catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [id, kind]);

  const counts = (rows ?? []).reduce<Record<string, number>>((m, r) => ({ ...m, [r.kind]: (m[r.kind] ?? 0) + 1 }), {});
  return (
    <RunShell run={run} error={error} tab="trace" online={online}>
      <p className="lead">Every agent step, LLM call, Qloo call and web lookup in this run, in order. Keys never appear here.</p>
      <div className="row" role="group" aria-label="Filter by kind" data-tour="trace-filter">
        {KINDS.map((k) => (
          <button key={k.key} className="btn-ghost btn-sm" aria-pressed={kind === k.key} onClick={() => setKind(k.key)}
            style={kind === k.key ? { background: "#000", color: "#fff", borderColor: "#000" } : undefined}>
            {k.label}{kind === "" && k.key && counts[k.key] ? ` · ${counts[k.key]}` : ""}
          </button>
        ))}
      </div>
      {!rows ? <Skeleton /> : rows.length === 0 ? <EmptyState title="Nothing recorded for this filter" /> : (
        <div className="table-wrap" data-tour="trace">
          <table className="t trace">
            <caption className="sr-only">Run trace</caption>
            <thead><tr><th scope="col">Time</th><th scope="col">Kind</th><th scope="col">Step</th><th scope="col">Call</th><th scope="col">Result</th></tr></thead>
            <tbody>
              {rows.map((t) => (
                <tr key={`${t.kind}-${t.id}`}>
                  <td className="mono" data-label="Time">{new Date(t.at).toLocaleTimeString()}</td>
                  <td data-label="Kind"><span className={`kind kind-${t.kind}`}>{t.kind}</span></td>
                  <td className="mono" data-label="Step">{t.step === "decision" ? <span className="tag">Decision</span> : t.step}</td>
                  <td className="cell-wide" data-label="Call">
                    <strong>{t.name}</strong>
                    {t.step === "decision" && (
                      <div className="stack-s" style={{ marginTop: 4 }}>
                        <p className="small"><span className="tag tag-line">{String((t.detail as { by?: string }).by)}</span> {String((t.detail as { reason?: string }).reason ?? "")}</p>
                        <Saw saw={(t.detail as { saw?: Record<string, unknown> }).saw ?? {}} />
                      </div>
                    )}
                    <details><summary>details</summary><pre>{JSON.stringify(t.detail, null, 2)}</pre></details>
                  </td>
                  <td className="small muted" data-label="Result">{brief(t)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Tour steps={TOUR} ready={!!rows} next={{ href: "/start", label: "Start your own run" }} />
    </RunShell>
  );
}
