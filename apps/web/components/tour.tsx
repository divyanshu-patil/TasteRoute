"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

export type TourStep = { target: string; title: string; body: string };
type Props = { steps: TourStep[]; ready: boolean; next?: { href: string; label: string } };

/** Guided walk-through, on when the URL has ?tour=1. Each step outlines an element marked data-tour="…". */
export function Tour(props: Props) {
  return <Suspense fallback={null}><TourInner {...props} /></Suspense>;
}

function TourInner({ steps, ready, next }: Props) {
  const on = useSearchParams().get("tour") === "1";
  const router = useRouter();
  const path = usePathname();
  const [live, setLive] = useState<TourStep[]>([]);
  const [i, setI] = useState(0);
  const card = useRef<HTMLDivElement>(null);
  const find = (s: TourStep) => document.querySelector<HTMLElement>(`[data-tour="${s.target}"]`);

  useEffect(() => {
    if (!on || !ready) return;
    const t = setTimeout(() => { setLive(steps.filter((s) => find(s))); setI(0); card.current?.focus(); }, 150);
    return () => clearTimeout(t);
    // steps are static per page; re-run only when the tour starts or the data arrives
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [on, ready]);

  const step = on ? live[i] : undefined;
  useEffect(() => {
    const el = step && find(step);
    if (!el) return;
    el.classList.add("tour-target");
    el.scrollIntoView({ behavior: "smooth", block: el.offsetHeight > window.innerHeight * 0.6 ? "start" : "center" });
    return () => el.classList.remove("tour-target");
  }, [step]);

  const close = () => router.replace(path, { scroll: false });
  useEffect(() => {
    if (!step) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (!step) return null;
  const last = i === live.length - 1;
  return (
    <div ref={card} className="tour" role="dialog" aria-labelledby="tour-title" aria-describedby="tour-body" tabIndex={-1}>
      <div className="row between">
        <span className="mono">TOUR · {String(i + 1).padStart(2, "0")} / {String(live.length).padStart(2, "0")}</span>
        <button className="link tour-skip" onClick={close}>Skip tour</button>
      </div>
      <h2 id="tour-title" className="h3">{step.title}</h2>
      <p id="tour-body">{step.body}</p>
      <div className="row between">
        <button className="btn-ghost btn-sm" onClick={() => setI(i - 1)} disabled={i === 0}>Back</button>
        {!last ? (
          <button className="btn btn-sm tour-next" onClick={() => setI(i + 1)}>Next</button>
        ) : next ? (
          <Link className="btn btn-sm tour-next" href={next.href}>{next.label} →</Link>
        ) : (
          <button className="btn btn-sm tour-next" onClick={close}>Done</button>
        )}
      </div>
    </div>
  );
}
