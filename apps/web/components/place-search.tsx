"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";

export type Hit = { label: string; detail?: string };

/**
 * Search on Enter or the button, then pick from a dropdown of plain-English suggestions.
 * Never searches as you type: Nominatim's usage policy forbids autocomplete.
 */
export function PlaceSearch<T extends Hit>({ id, label, placeholder, help, search, onPick }: {
  id: string;
  label: string;
  placeholder: string;
  help?: string;
  search: (q: string) => Promise<T[]>;
  onPick: (hit: T) => void;
}) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<T[] | null>(null);
  const [busy, setBusy] = useState(false);
  const box = useRef<HTMLFormElement>(null);

  useEffect(() => {
    if (!hits) return;
    const away = (e: MouseEvent) => box.current && !box.current.contains(e.target as Node) && setHits(null);
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [hits]);

  const go = async (e: FormEvent) => {
    e.preventDefault();
    if (q.trim().length < 3) return;
    setBusy(true);
    try {
      setHits(await search(q.trim()));
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
            onChange={(e) => { setQ(e.target.value); setHits(null); }} />
        </label>
        <button className="btn" disabled={busy || q.trim().length < 3}>{busy ? "Searching…" : "Search"}</button>
        {hits && (
          <ul className="suggest" aria-label={`Suggestions for ${q}`}>
            {hits.length === 0 && <li className="suggest-empty">No matches. Try a street, a neighbourhood or a nearby landmark.</li>}
            {hits.map((h, i) => (
              <li key={`${h.label}-${i}`}>
                <button type="button" onClick={() => { onPick(h); setQ(h.label); setHits(null); }}>
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
