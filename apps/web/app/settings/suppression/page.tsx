"use client";

import { useEffect, useState } from "react";
import { Banner, EmptyState, Skeleton } from "../../../components/ui";
import { ApiError, api, type S } from "../../../lib/api";

export default function Suppression() {
  const [list, setList] = useState<S["SuppressionOut"][] | null>(null);
  const [kind, setKind] = useState<"email" | "domain">("domain");
  const [value, setValue] = useState("");
  const [reason, setReason] = useState<"manual" | "opt_out" | "bounced">("opt_out");
  const [q, setQ] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let alive = true;
    api<S["SuppressionOut"][]>(`/v1/suppressions${q ? `?q=${encodeURIComponent(q)}` : ""}`).then((l) => alive && setList(l)).catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [q, version]);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    try {
      await api("/v1/suppressions", { method: "POST", body: { kind, value, reason } });
      setValue("");
      setVersion((v) => v + 1);
    } catch (x) {
      setErr(x instanceof ApiError ? x.detail || x.title : "Could not add");
    }
  };
  const remove = async (id: string) => {
    await api(`/v1/suppressions/${id}`, { method: "DELETE" }).catch(() => undefined);
    setVersion((v) => v + 1);
  };

  return (
    <div className="wrap stack" style={{ gap: 32 }}>
      <h1 className="display d-l">Do-not-contact list</h1>
      <p className="lead">Emails and domains here are skipped in contact lookups, drafts and exports. Add anyone who replies “no thanks”.</p>
      <form className="card stack" onSubmit={add}>
        <div className="row" style={{ alignItems: "flex-end" }}>
          <label className="field" style={{ minWidth: 140 }}>
            <span>Type</span>
            <select className="select" value={kind} onChange={(e) => setKind(e.target.value as "email" | "domain")}>
              <option value="domain">Domain</option>
              <option value="email">Email</option>
            </select>
          </label>
          <label className="field" style={{ flex: 1, minWidth: 220 }}>
            <span>{kind === "email" ? "Email address" : "Domain"}</span>
            <input className="input" required value={value} placeholder={kind === "email" ? "owner@cafe-example.com" : "cafe-example.com"} onChange={(e) => setValue(e.target.value)} />
          </label>
          <label className="field" style={{ minWidth: 160 }}>
            <span>Reason</span>
            <select className="select" value={reason} onChange={(e) => setReason(e.target.value as typeof reason)}>
              <option value="opt_out">Opted out</option>
              <option value="bounced">Bounced</option>
              <option value="manual">Other</option>
            </select>
          </label>
          <button className="btn" type="submit">Add</button>
        </div>
        {err && <Banner tone="warn">{err}</Banner>}
      </form>
      <label className="field" style={{ maxWidth: 360 }}>
        <span>Search</span>
        <input className="input" value={q} onChange={(e) => setQ(e.target.value)} />
      </label>
      {!list ? <Skeleton rows={3} /> : list.length === 0 ? <EmptyState title="The list is empty" /> : (
        <ul className="stack-s" style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {list.map((s) => (
            <li key={s.id} className="card row between" style={{ padding: "14px 20px" }}>
              <span className="row"><span className="tag tag-mist">{s.kind}</span><strong>{s.value}</strong><span className="mono faint">{s.reason.replace("_", " ")}</span></span>
              <button className="btn-ghost btn-sm" onClick={() => remove(s.id)} aria-label={`Remove ${s.value}`}>Remove</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
