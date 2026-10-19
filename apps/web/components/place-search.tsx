"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";

export type Hit = { label: string; detail?: string };

/**
 * A dropdown of plain-English places: `suggest` runs as you type (debounced, Photon), and Enter or the button runs
 * the full `search` (Nominatim, which forbids autocomplete, so it never runs per keystroke).
 */
export function PlaceSearch<T extends Hit>({ id, label, placeholder, help, search, suggest, onPick }: {
  id: string;
  label: string;
  placeholder: string;
  help?: string;
  search: (q: string) => Promise<T[]>;
  suggest?: (q: string) => Promise<T[]>;
  onPick: (hit: T) => void;
}) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<T[] | null>(null);
  const [busy, setBusy] = useState(false);
  const box = useRef<HTMLFormElement>(null);
  const seq = useRef(0); // only the newest request may fill the dropdown
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);

  const type = (v: string) => {
    setQ(v);
    setHits(null);
    clearTimeout(timer.current);
    const n = ++seq.current;
    if (!suggest || v.trim().length < 3) return;
    timer.current = setTimeout(() => {
      suggest(v.trim()).then((h) => n === seq.current && setHits(h.length ? h : null)).catch(() => {}); // Enter still searches
    }, 350);
  };

  useEffect(() => {
    if (!hits) return;
    const away = (e: MouseEvent) => box.current && !box.current.contains(e.target as Node) && setHits(null);
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [hits]);

  const go = async (e: FormEvent) => {
    e.preventDefault();
    if (q.trim().length < 3) return;
    clearTimeout(timer.current);
    const n = ++seq.current;
    setBusy(true);
    try {
      const h = await search(q.trim());
      if (n === seq.current) setHits(h);
    } catch {
      setHits(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form ref={box} className="search" role="search" onSubmit={go} onKeyDown={(e) => e.key === "Escape" && setHits(null)}>
      <div className="search-bar">
        <label className="field" htmlFor={id}>
          <span>{label}</span>
          <input id={id} className="input" value={q} placeholder={placeholder} autoComplete="off" aria-describedby={help ? `${id}-help` : undefined}
            onChange={(e) => type(e.target.value)} />
        </label>
        <button className="btn" disabled={busy || q.trim().length < 3}>{busy ? "Searching…" : "Search"}</button>
        {hits && (
          <ul className="suggest" aria-label={`Suggestions for ${q}`}>
            {hits.length === 0 && <li className="suggest-empty">No matches. Try a street, a neighbourhood or a nearby landmark.</li>}
            {hits.map((h, i) => (
              <li key={`${h.label}-${i}`}>
                <button type="button" onClick={() => { seq.current++; onPick(h); setQ(h.label); setHits(null); }}>
                  <strong>{h.label}</strong>
                  {h.detail && <span className="mono">{h.detail}</span>}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      {help && <p id={`${id}-help`} className="small faint">{help}</p>}
    </form>
  );
}
